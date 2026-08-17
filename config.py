import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Use random hex as fallback secret if env is missing to prevent security issues in prod
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 30 * 1024 * 1024)) # 30 MB limit
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    
    # Use system /tmp directory for ephemeral, PaaS-friendly storage (avoids permission issues)
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'tts_uploads')
    GENERATED_FOLDER = os.path.join(tempfile.gettempdir(), 'tts_generated')

    # Separate folder for the voice preview cache. It is intentionally NOT the
    # same folder as GENERATED_FOLDER: preview clips are short, shared between
    # users and content-addressed, while generated audio is per-session.
    #
    # NOTE ON RENDER: this is ephemeral filesystem. Render replaces the
    # container on every deploy, restart or scale event, so this cache only
    # lives as long as the running instance. No external storage is used.
    PREVIEW_FOLDER = os.path.join(tempfile.gettempdir(), 'tts_previews')
    # Previews are deterministic and cheap to regenerate; keeping them for a
    # day is enough to be useful without letting /tmp grow unbounded.
    PREVIEW_MAX_AGE_SECONDS = int(os.environ.get('PREVIEW_MAX_AGE_SECONDS', 24 * 3600))

    # Secure Cookies settings for production environments
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV', 'development') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Ensure session is always saved and refreshed to avoid CSRF expiration
    SESSION_REFRESH_EACH_REQUEST = True
    PERMANENT_SESSION_LIFETIME = 3600 # 1 hour

    # Transcription Settings (OpenAI API)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_TRANSCRIBE_MODEL = os.environ.get('OPENAI_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe')

    # Ensure directories exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FOLDER, exist_ok=True)
    os.makedirs(PREVIEW_FOLDER, exist_ok=True)
