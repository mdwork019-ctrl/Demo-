# Sales Transcription and Processing System

## Overview
This system automates the processing of sales meeting recordings. It monitors a Google Spreadsheet for new meeting links, downloads the audio, transcribes it using the Groq API, and generates formatted transcripts via the Gemini API. Processed files are uploaded to Google Drive, and the spreadsheet is updated with the corresponding links.

## Core Features
- Automated monitoring of Google Sheets for unprocessed meeting records.
- Audio extraction and compression for optimized API transmission.
- High-accuracy transcription using Whisper (via Groq).
- Context-aware speaker diarization and transcript formatting.
- Automated file management and synchronization with Google Drive.

## System Requirements
- Python 3.8+
- FFmpeg (required for audio processing)
- Google Cloud Service Account credentials
- API Keys for Groq and Google Gemini

## Step-by-Step Setup and Execution

### 1. Environment Preparation
Ensure Python 3.8 or higher is installed on your system.
Install the required system dependecy, **FFmpeg**, and ensure it is available in your system's PATH.

### 2. Install Dependencies
Execute the following command to install the necessary Python libraries:
```bash
pip install gspread google-auth-oauthlib google-api-python-client requests groq google-generativeai python-dotenv
```

### 3. Google API Configuration
1. Access the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and enable the **Google Drive API** and **Google Sheets API**.
3. Create an **OAuth 2.0 Client ID** (Desktop Application).
4. Download the JSON credential file, rename it to `client_secret.json`, and place it in the project root directory.

### 4. API Key Configuration
Create a `.env` file in the root directory and add your respective API keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

### 5. Execution (Primary Entry Point)
The entire system is managed through a single execution point. To initiate the authentication flow and start the processing pipeline, run:
```bash
python sales_processor.py
```
**Note:** On the first run, this will open a browser window for Google Authentication. Once authenticated, a `token.json` file will be created, and the script will proceed to process the spreadsheet rows automatically.

### 6. Automated Processing
Once the script is running, it performs the following:
1. Scans the configured Google Sheet from row 2.
2. Identifies rows with recordings that lack transcripts.
3. Downloads, processes, and uploads the results.
4. Updates the spreadsheet in real-time.

No other scripts need to be executed manually.

## Security
- Credentials (`token.json`, `client_secret.json`) and local environmental variables (`.env`) are excluded from version control via `.gitignore`.
- Always ensure API keys are kept confidential.
