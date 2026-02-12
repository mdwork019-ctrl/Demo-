import gspread
from google_auth import get_credentials
import config
import requests
import os
import time
import json
import subprocess
import google.generativeai as genai
from datetime import datetime

# Configuration
SALES_SHEET_ID = "1gXHwbzYipr07Q1lEza4rD5KwMjHRh1aG3VBCec3URBw"
SALES_ARCHIVE_FOLDER_ID = "1cj9FktrdxXvjPPXbPak5CtBEbmBscaOv"
TEMP_DIR = "temp_sales_processing"

# Transcription logic using Groq API
def local_transcribe_groq(audio_path):
    """
    Transcribes audio using Groq Whisper. Returns (text, duration).
    """
    if not config.GROQ_API_KEY: 
        print("Error: GROQ_API_KEY missing in configuration")
        return None, 0
    from groq import Groq
    import re
    client = Groq(api_key=config.GROQ_API_KEY)
    
    lock_file = "./.sales_groq.lock"
    last_call_file = "./.sales_groq_last.txt"

    print(f"Checking lock: {lock_file}")
    while os.path.exists(lock_file):
        if time.time() - os.path.getmtime(lock_file) > 120: 
            os.remove(lock_file)
        time.sleep(2)
    
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            with open(lock_file, "w") as f: 
                f.write("lock")
            
            if os.path.exists(last_call_file):
                with open(last_call_file, "r") as f: 
                    last_time = float(f.read().strip())
                wait = 90 - (time.time() - last_time)
                if wait > 0: 
                    print(f"Applying rate limit delay: {wait:.1f}s")
                    time.sleep(wait)

            print(f"Requesting Groq transcription (Attempt {attempt}) for {audio_path}")
            with open(audio_path, "rb") as file:
                translation = client.audio.translations.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                )
            
            with open(last_call_file, "w") as f: 
                f.write(str(time.time()))
            
            duration = getattr(translation, 'duration', 0)
            return translation.text, duration

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg and attempt < max_retries:
                print(f"Rate limit hit. Retrying in 60s (Attempt {attempt}/{max_retries})")
                time.sleep(60) 
            else:
                print(f"Transcription failed: {e}")
                return None, 0
        finally:
            if os.path.exists(lock_file): 
                os.remove(lock_file)
    return None, 0

def upload_to_sales_folder(file_path, meeting_title, mime_type):
    """
    Uploads a file to the defined Google Drive folder.
    """
    creds = get_credentials()
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    service = build('drive', 'v3', credentials=creds)
    
    basename = os.path.basename(file_path)
    ext = os.path.splitext(basename)[1]
    drive_filename = f"{meeting_title}{ext}"
    
    file_metadata = {
        'name': drive_filename,
        'parents': [SALES_ARCHIVE_FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    
    print(f"Uploading {drive_filename} to Drive")
    file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    try:
        service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
    except: 
        pass
    
    return file.get('webViewLink')

def run_heavy_sales_processor():
    """
    Main entry point for processing the sales recordings backlog.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    print("Initiating Sales Processing Pipeline")
    
    creds = get_credentials()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SALES_SHEET_ID)
    ws = sh.get_worksheet(0)
    
    records = ws.get_all_records()
    headers = ws.row_values(1)
    col_map = {h: i+1 for i, h in enumerate(headers)}

    for i, row in enumerate(records):
        row_idx = i + 2
        if row_idx < 2:
            continue
            
        rec_url = str(row.get('Recording Link_Uniview', '')).strip()
        trans_link = str(row.get('Transcript_link', '')).strip()
        duration_val = str(row.get('Duration', '')).strip()
        
        # Case A: Full processing required
        if rec_url and (not trans_link or trans_link == "N/A" or trans_link == ""):
            process_row(ws, row_idx, row, col_map, full_mode=True)
            time.sleep(15)
        
        # Case B: Duration backfill required
        elif rec_url and trans_link and (not duration_val or duration_val == "N/A" or duration_val == ""):
            print(f"Backfilling duration for row {row_idx}")
            process_row(ws, row_idx, row, col_map, full_mode=False)
            time.sleep(2)
        else:
            if rec_url: 
                print(f"Row {row_idx} already processed. Skipping.")

def process_row(ws, row_idx, row, col_map, full_mode=True):
    """
    Processes a single row from the spreadsheet.
    """
    emp_email = str(row.get('Emp Email ID', 'NBH')).strip()
    emp_name = emp_email.split('@')[0].replace('.', ' ').title()
    poc_name = str(row.get('POC Name', 'Customer')).strip()
    raw_title = str(row.get('Meeting Title', f"Meeting_{row_idx}")).strip()
    
    if "||" in raw_title:
        title = raw_title.split("||")[-1].strip()
    else:
        title = raw_title
    
    title = "".join(c for c in title if c not in r'\/:*?"<>|').replace(' ', '_')
    rec_url = str(row.get('Recording Link_Uniview', '')).strip()
    
    print(f"Processing: {title}")
    ext = ".mp4" if "firebase" in rec_url.lower() else ".3gp"
    raw_path = os.path.join(TEMP_DIR, f"temp_{row_idx}{ext}")
    
    try:
        # Download resource
        resp = requests.get(rec_url, stream=True, timeout=60)
        with open(raw_path, 'wb') as f:
            for chunk in resp.iter_content(8192): 
                f.write(chunk)
            
        # Get duration using ffprobe
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', raw_path], 
                                capture_output=True, text=True)
        try:
            duration_sec = float(result.stdout.strip())
            duration_formatted = f"{int(duration_sec // 60)}m {int(duration_sec % 60)}s"
        except:
            duration_formatted = "N/A"
            
        if full_mode:
            # Compression and transcription
            compressed_path = os.path.join(TEMP_DIR, f"{title}.mp3")
            subprocess.run(['ffmpeg', '-y', '-i', raw_path, '-vn', '-ac', '1', '-ar', '16000', '-ab', '16k', compressed_path], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
            
            raw_text, _ = local_transcribe_groq(compressed_path)
            
            if raw_text:
                genai.configure(api_key=config.GEMINI_API_KEY)
                model = genai.GenerativeModel(config.GEMINI_MODEL)
                
                d_prompt = f"""You are a professional sales transcript editor for NoBrokerHood (NBH). 

Product: Society Management App.
Objective: NBH Sales Representative ({emp_name}) is pitching to {poc_name}.

CAST:
- NBH ({emp_name}): Sales representative.
- Customer ({poc_name}): Client POC.

FORMATTING:
1. Double-space between speaker turns.
2. Labels: **NBH ({emp_name}):** and **{poc_name}:**.
3. New line after every full stop.
4. Filter out repetition artifacts or hallucinations.

RAW TEXT:
{raw_text}"""
                diarized_text = model.generate_content(d_prompt).text
                
                txt_path = os.path.join(TEMP_DIR, f"{title}.txt")
                with open(txt_path, "w", encoding="utf-8") as f: 
                    f.write(diarized_text)
                
                t_link = upload_to_sales_folder(txt_path, title, "text/plain")
                m_link = upload_to_sales_folder(compressed_path, title, "audio/mpeg")
                
                if 'Transcript_link' in col_map: 
                    ws.update_cell(row_idx, col_map['Transcript_link'], t_link)
                if 'MP3_Formate' in col_map: 
                    ws.update_cell(row_idx, col_map['MP3_Formate'], m_link)
                if 'Duration' in col_map: 
                    ws.update_cell(row_idx, col_map['Duration'], duration_formatted)
                
                if os.path.exists(compressed_path): os.remove(compressed_path)
                if os.path.exists(txt_path): os.remove(txt_path)
        else:
            if 'Duration' in col_map: 
                ws.update_cell(row_idx, col_map['Duration'], duration_formatted)
            
    except Exception as e:
        print(f"Failed to process row {row_idx}: {e}")
    finally:
        if os.path.exists(raw_path): 
            os.remove(raw_path)

if __name__ == "__main__":
    run_heavy_sales_processor()
