import os
from pathlib import Path
from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load dedicated secret files first; .env provides non-secret defaults
load_dotenv(PROJECT_ROOT / '.cred')
load_dotenv(PROJECT_ROOT / '.key')
load_dotenv(PROJECT_ROOT / '.env')

# General properties under .env file
LINKEDIN_URL = os.getenv("LINKEDIN_URL", "https://in.linkedin.com/")
LINKED_IN_SEARCH_URL = os.environ.get("LINKED_IN_SEARCH_URL", "https://in.linkedin.com/")
SESSION_FILE = os.getenv("SESSION_FILE", "linked-in-session.json")
CHROME_PATH = os.getenv("CHROME_PATH", "chrome")
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", None)
EASYOCR_MODEL_DIR = os.getenv("EASYOCR_MODEL_DIR", "")
PROXY_URL = os.getenv("PROXY_URL", "")

# Encrypted properties in .cred file
LINKEDIN_USER = os.getenv("LINKEDIN_USER", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
ENCODE_PROXY = os.getenv("ENCODE_PROXY", "")

# Key for encryption in .key file
DECRYPTION_KEY = "key" if os.getenv("DECRYPTION_KEY", "") == "" else os.getenv("DECRYPTION_KEY", "key")

def validate_config():
    if not LINKEDIN_USER or not LINKEDIN_PASSWORD:
        raise Exception("LINKEDIN_USER and LINKEDIN_PASSWORD must be set")

def set_key_to_file(key_file_type, key_name, key_value):
    # Write the generated key and encryption data to file
    key_file = Path(PROJECT_ROOT / f".{key_file_type}")
    set_key(key_file, key_name, key_value)