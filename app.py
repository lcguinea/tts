import os
import uuid
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, session, url_for
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from utils import extract_text_from_file, generate_mp3_sync, cleanup_old_files
import logging
from openai import OpenAI
from werkzeug.exceptions import HTTPException

# Initialize OpenAI Client (Lazy initialization or global)
client = None
def get_openai_client():
    global client
    if client is None:
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Protection & Rate Limiting
csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=app.config['RATELIMIT_STORAGE_URL']
)



ALLOWED_EXTENSIONS = {'.txt', '.rtf'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.webm', '.ogg', '.opus', '.mp4'}

def allowed_file(filename):
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def allowed_audio_file(filename):
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

# Local model loader removed in favor of OpenAI API

@app.before_request
def assign_session_id():
    """Ensure every session has a unique ID and do occasional cleanups."""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    # Perform cleanup (files older than 1 hour)
    cleanup_old_files([app.config['UPLOAD_FOLDER'], app.config['GENERATED_FOLDER']], max_age_seconds=3600)

@app.route('/')
def index():
    # Pass csrf_token to be used by our frontend AJAX requests
    return render_template('index.html', csrf_token=generate_csrf())

@app.route('/api/generate', methods=['POST'])
@limiter.limit("10 per minute")
def generate_audio():
    user_id = session.get('user_id')
    logger.info(f"--- Generate Request Started (User: {user_id}) ---")
    logger.info(f"Context: Content-Type={request.content_type}, Remote-Addr={request.remote_addr}")
    
    # Log raw form and files
    logger.info(f"Form Keys: {list(request.form.keys())}")
    logger.info(f"Files Keys: {list(request.files.keys())}")

    text_content = request.form.get('text_content', '').strip()
    uploaded_file = request.files.get('file')
    
    final_text = ""
    
    # Priority: Textarea > File Upload
    if text_content:
        final_text = text_content
        logger.info(f"Using Textarea (Length: {len(final_text)})")
    elif uploaded_file and uploaded_file.filename != '':
        logger.info(f"Using Uploaded File: {uploaded_file.filename}")
        if not allowed_file(uploaded_file.filename):
            logger.warning(f"Invalid file extension: {uploaded_file.filename}")
            return jsonify({'error': 'Formato de archivo inválido. Sube .txt o .rtf'}), 400
            
        filename = secure_filename(uploaded_file.filename)
        safe_filename = f"{user_id}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        
        uploaded_file.save(filepath)
        try:
            extracted_res = extract_text_from_file(filepath)
            if extracted_res.startswith("Error:"):
                logger.error(f"Text extraction business error: {extracted_res}")
                return jsonify({'error': extracted_res}), 400
            final_text = extracted_res
            logger.info(f"Extracted Text (Length: {len(final_text)})")
        except Exception as e:
            logger.error(f"Text extraction failed: {str(e)}")
            return jsonify({'error': f'Error técnico al procesar archivo: {str(e)}'}), 400
            
    if not final_text:
        logger.warning("No text provided in request (both textarea and file were empty).")
        return jsonify({'error': 'Por favor, introduce texto o sube un archivo válido.'}), 400

    # Retrieve and Normalize TTS parameters
    voice = request.form.get('voice', '').strip()
    if not voice:
        voice = 'es-ES-AlvaroNeural'
        
    # Support list of voices we show in UI
    ALLOWED_VOICES = {
        'es-ES-AlvaroNeural', 'es-MX-JorgeNeural', 'es-AR-TomasNeural', 
        'es-CO-GonzaloNeural', 'es-US-AlonsoNeural', 'es-ES-ElviraNeural'
    }
    if voice not in ALLOWED_VOICES:
        logger.warning(f"Unsupported voice requested: {voice}. Defaulting to Alvaro.")
        voice = 'es-ES-AlvaroNeural'
    
    try:
        # Better fallback logic for parameters
        def get_safe_int(key, default):
            val = request.form.get(key, '').strip()
            if not val:
                return default
            return int(float(val)) # float then int to handle inputs like "0.0"

        rate = get_safe_int('rate', 0)
        pitch = get_safe_int('pitch', 0)
        volume = get_safe_int('volume', 0)
    except Exception as e:
        logger.error(f"Parameter parsing error: {str(e)}")
        return jsonify({'error': 'Parámetros de audio inválidos. Deben ser números.'}), 400
    
    # Constrain values
    rate = max(-100, min(100, rate))
    pitch = max(-20, min(20, pitch))
    volume = max(-100, min(100, volume))
    
    logger.info(f"Parameters: voice={voice}, rate={rate}, pitch={pitch}, volume={volume}")

    output_filename = f"{user_id}_{uuid.uuid4().hex[:8]}.mp3"
    output_path = os.path.join(app.config['GENERATED_FOLDER'], output_filename)
    
    try:
        generate_mp3_sync(final_text, voice, rate, pitch, volume, output_path)
    except Exception as e:
        err_msg = str(e)
        logger.error(f"edge-tts generation failed: {err_msg}")
        # Return the actual error message if it's related to patterns
        if "pattern" in err_msg.lower():
            return jsonify({'error': f'Error en parámetros de voz: {err_msg}'}), 400
        return jsonify({'error': 'Error interno al generar el audio.'}), 500
        
    audio_url = url_for('get_audio', filename=output_filename)
    download_url = url_for('download_audio', filename=output_filename)
    
    logger.info(f"Success: Audio generated at {audio_url}")
    return jsonify({
        'success': True,
        'audio_url': audio_url,
        'download_url': download_url,
        'filename': output_filename
    })

@app.route('/api/transcribe', methods=['POST'])
@limiter.limit("5 per minute")
def transcribe_audio():
    user_id = session.get('user_id')
    logger.info(f"--- Transcribe Request Started (User: {user_id}) ---")
    
    if not app.config.get('OPENAI_API_KEY'):
        logger.error("OPENAI_API_KEY is not configured.")
        return jsonify({'error': 'La transcripción no está configurada (API Key faltante).'}), 500

    if 'audio' not in request.files:
        return jsonify({'error': 'No se proporcionó ningún archivo de audio.'}), 400
        
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'Archivo de audio vacío.'}), 400

    if not allowed_audio_file(audio_file.filename):
        return jsonify({'error': f'Formato no soportado. Usa: {", ".join(ALLOWED_AUDIO_EXTENSIONS)}'}), 400

    # Save file temporarily for API transmission
    filename = secure_filename(audio_file.filename)
    safe_filename = f"transcribe_{user_id}_{uuid.uuid4().hex[:8]}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    
    try:
        audio_file.save(filepath)
        logger.info(f"Audio saved to {filepath}. Sending to OpenAI...")
        
        # Get OpenAI Client
        openai_client = get_openai_client()
        
        # Perform API Transcription
        with open(filepath, "rb") as audio_binary:
            transcription = openai_client.audio.transcriptions.create(
                model=app.config.get('OPENAI_TRANSCRIBE_MODEL'),
                file=audio_binary
            )
        
        transcription_text = transcription.text.strip()
        logger.info(f"Transcription complete (Length: {len(transcription_text)})")
        
        return jsonify({
            'success': True,
            'text': transcription_text
        })

    except Exception as e:
        err_msg = str(e).lower()
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        
        # Categorize common API errors
        if "invalid_api_key" in err_msg or "401" in err_msg:
            return jsonify({'error': 'Error de autenticación: la clave de OpenAI es inválida o expiró.'}), 401
        if "quota" in err_msg or "429" in err_msg:
            return jsonify({'error': 'Límite de cuota excedido. Por favor, revisa tus créditos de OpenAI.'}), 429
        if "timeout" in err_msg:
            return jsonify({'error': 'Tiempo de espera agotado al conectar con OpenAI.'}), 504
            
        return jsonify({'error': f'Error en el servicio de OpenAI: {str(e)}'}), 500
    finally:
        # Cleanup the temporary file immediately
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"Temporary file removed: {filepath}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup temp file {filepath}: {str(cleanup_err)}")

@app.route('/api/audio/<filename>')
def get_audio(filename):
    """Serve the generated MP3 for streaming/playing"""
    user_id = session.get('user_id')
    if not secure_filename(filename).startswith(f"{user_id}_"):
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    return send_from_directory(app.config['GENERATED_FOLDER'], secure_filename(filename))

@app.route('/api/download/<filename>')
def download_audio(filename):
    """Serve the generated MP3 as a forced download"""
    user_id = session.get('user_id')
    if not secure_filename(filename).startswith(f"{user_id}_"):
        return jsonify({'error': 'Acceso denegado.'}), 403
        
    return send_from_directory(
        app.config['GENERATED_FOLDER'], 
        secure_filename(filename), 
        as_attachment=True, 
        download_name="tts_audio.mp3"
    )

# --- Global Error Handlers (Ensure JSON for all API errors) ---

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.error(f"CSRF Error: {e.description} (URL: {request.url})")
    # If a post fails CSRF, it might be due to a stale session or cookie block
    return jsonify({
        'error': 'Error de validación (CSRF). Por favor, refresca la página o habilita las cookies.',
        'details': e.description
    }), 400

@app.errorhandler(400)
def handle_bad_request(e):
    # Log the specific underlying reason (important for CSRF or form problems)
    reason = getattr(e, 'description', 'error desconocido')
    logger.error(f"400 Error: {reason}")
    return jsonify({
        'error': 'Solicitud incorrecta (posible error CSRF o campos inesperados).',
        'details': str(reason)
    }), 400

@app.errorhandler(413)
def handle_payload_too_large(e):
    logger.error(f"413 Error: {str(e)}")
    return jsonify({'error': 'Archivo demasiado grande. El límite es 10MB.'}), 413

@app.errorhandler(429)
def handle_ratelimit(e):
    logger.error(f"429 Error: {str(e)}")
    return jsonify({'error': 'Demasiadas solicitudes. Por favor, espera un momento.'}), 429

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    
    logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
    return jsonify({'error': 'Error interno del servidor.'}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
