import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Use random hex as fallback secret if env is missing to prevent security issues in prod
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024)) # 10 MB limit
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    
    # Use system /tmp directory for ephemeral, PaaS-friendly storage (avoids permission issues)
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'tts_uploads')
    GENERATED_FOLDER = os.path.join(tempfile.gettempdir(), 'tts_generated')
    
    # Secure Cookies settings for production environments
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV', 'development') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Ensure session is always saved and refreshed to avoid CSRF expiration
    SESSION_REFRESH_EACH_REQUEST = True
    PERMANENT_SESSION_LIFETIME = 3600 # 1 hour

    # Ensure directories exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FOLDER, exist_ok=True)
