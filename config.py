import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AI Configuration
GEMINI_MODEL = "gemini-2.5-flash" 

# API Authorization Scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets"
]

# API Credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
