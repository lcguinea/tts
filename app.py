import os
import uuid
import datetime
import time
import re
import hashlib
import tempfile
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, session, url_for
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from voices import (
    VOICE_GROUPS,
    ALLOWED_VOICE_IDS,
    DEFAULT_VOICE,
    PREVIEW_TEXT,
    PREVIEW_RATE,
    PREVIEW_PITCH,
    PREVIEW_VOLUME,
    is_allowed as is_allowed_voice,
)
from utils import extract_text_from_file, generate_mp3_sync, cleanup_old_files, get_audio_duration, split_audio_ffmpeg, deduplicate_text, optimize_text_for_tts
import logging
from openai import OpenAI
from werkzeug.exceptions import HTTPException
import subprocess

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



ALLOWED_EXTENSIONS = {'.txt', '.rtf', '.docx', '.pdf', '.md', '.csv', '.html', '.htm'}
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
    # The preview cache is deterministic and shared, so it gets a longer TTL.
    cleanup_old_files([app.config['PREVIEW_FOLDER']],
                      max_age_seconds=app.config['PREVIEW_MAX_AGE_SECONDS'])

@app.route('/')
def index():
    # Pass csrf_token to be used by our frontend AJAX requests
    return render_template(
        'index.html',
        csrf_token=generate_csrf(),
        voice_groups=VOICE_GROUPS,
        default_voice=DEFAULT_VOICE,
    )

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

    # Optimization Step
    use_ai = request.form.get('use_ai') == 'true'
    openai_client_instance = get_openai_client() if use_ai else None
    final_text = optimize_text_for_tts(final_text, use_ai=use_ai, openai_client=openai_client_instance)

    # Retrieve and Normalize TTS parameters
    voice = request.form.get('voice', '').strip()
    if not voice:
        voice = DEFAULT_VOICE

    # Single shared catalog (voices.py), used by generation, preview and template
    if voice not in ALLOWED_VOICE_IDS:
        logger.warning(f"Unsupported voice requested: {voice}. Defaulting to {DEFAULT_VOICE}.")
        voice = DEFAULT_VOICE
    
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
    
    if len(final_text) > 8000:
        logger.info(f"Long text generation detected: {len(final_text)} characters.")

    start_gen_time = time.time()
    try:
        generate_mp3_sync(final_text, voice, rate, pitch, volume, output_path)
        total_gen_time = time.time() - start_gen_time
        logger.info(f"Generation complete. Duration: {total_gen_time:.2f}s for {len(final_text)} chars.")
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

    ext_detectada = os.path.splitext(audio_file.filename)[1].lower()
    mime_type_recibido = audio_file.content_type
    logger.info(f"Archivo recibido: {audio_file.filename}, Extensión detectada: {ext_detectada}, MIME type recibido: {mime_type_recibido}")

    # Save file temporarily for API transmission
    filename = secure_filename(audio_file.filename)
    safe_filename = f"transcribe_{user_id}_{uuid.uuid4().hex[:8]}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    logger.info(f"Ruta temporal asignada: {filepath}")
    
    try:
        audio_file.save(filepath)
        
        # Check duration for chunking
        duration = get_audio_duration(filepath)
        logger.info(f"Audio saved to {filepath}. Duration: {duration:.2f}s")
        
        # Si la duración es 0 y no se pudo obtener, podría ser corrupto, pero intentaremos
        # enviarlo o convertirlo de todos modos. Si falla, el bloque except lo capturará.
        
        # Determine if we need chunking (5 min = 300s)
        # Using 305s as threshold to avoid splitting very close ones
        CHUNK_THRESHOLD = 300 
        OVERLAP = 5
        
        openai_client = get_openai_client()
        final_transcription = ""
        
        if duration > CHUNK_THRESHOLD + OVERLAP:
            logger.info(f"Long audio detected ({duration:.2f}s). Processing in chunks of {CHUNK_THRESHOLD}s...")
            
            # Create a temporary directory for chunks
            chunk_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"chunks_{uuid.uuid4().hex[:8]}")
            os.makedirs(chunk_dir, exist_ok=True)
            
            try:
                chunks = split_audio_ffmpeg(filepath, chunk_dir, chunk_duration=CHUNK_THRESHOLD, overlap=OVERLAP)
                
                previous_text = ""
                for idx, chunk_path in enumerate(chunks):
                    logger.info(f"Processing chunk {idx+1}/{len(chunks)}: {chunk_path}")
                    with open(chunk_path, "rb") as audio_binary:
                        chunk_res = openai_client.audio.transcriptions.create(
                            model=app.config.get('OPENAI_TRANSCRIBE_MODEL'),
                            file=audio_binary
                        )
                    
                    chunk_text = chunk_res.text.strip()
                    if not final_transcription:
                        final_transcription = chunk_text
                    else:
                        # Deduplicate using overlap logic
                        deduped = deduplicate_text(previous_text, chunk_text, max_overlap_words=20)
                        final_transcription += " " + deduped
                    
                    previous_text = chunk_text
                    
                logger.info(f"Chunked transcription complete (Total length: {len(final_transcription)})")
                
            finally:
                # Cleanup chunks directory
                if os.path.exists(chunk_dir):
                    import shutil
                    shutil.rmtree(chunk_dir)
                    logger.info(f"Cleanup: Removed chunk directory {chunk_dir}")
        else:
            # Single call processing
            logger.info("Sending audio directly to OpenAI...")
            try:
                with open(filepath, "rb") as audio_binary:
                    transcription = openai_client.audio.transcriptions.create(
                        model=app.config.get('OPENAI_TRANSCRIBE_MODEL'),
                        file=audio_binary
                    )
                final_transcription = transcription.text.strip()
                logger.info("Se transcribió directamente sin conversión previa.")
            except Exception as direct_e:
                if ext_detectada == '.opus' or filepath.lower().endswith('.opus'):
                    logger.warning(f"Fallo directo con .opus. Convirtiendo a .mp3 temporalmente usando ffmpeg. Error: {str(direct_e)}")
                    mp3_filepath = filepath + ".mp3"
                    try:
                        import subprocess
                        subprocess.run(['ffmpeg', '-y', '-i', filepath, '-q:a', '2', mp3_filepath], capture_output=True, check=True)
                        logger.info(f"Archivo convertido temporalmente a: {mp3_filepath}")
                        with open(mp3_filepath, "rb") as audio_binary:
                            transcription = openai_client.audio.transcriptions.create(
                                model=app.config.get('OPENAI_TRANSCRIBE_MODEL'),
                                file=audio_binary
                            )
                        final_transcription = transcription.text.strip()
                        logger.info("Se transcribió correctamente tras convertir.")
                    except subprocess.CalledProcessError:
                        logger.error("Fallo al convertir .opus a .mp3. Archivo corrupto o inválido.")
                        return jsonify({'error': 'El archivo .opus parece estar corrupto o tiene un formato inválido.'}), 400
                    finally:
                        if os.path.exists(mp3_filepath):
                            os.remove(mp3_filepath)
                            logger.info(f"Cleanup: Temporary converted file removed: {mp3_filepath}")
                else:
                    raise direct_e
            logger.info(f"Transcription complete (Length: {len(final_transcription)}). Resultado de la transcripción exitoso.")
        
        return jsonify({
            'success': True,
            'text': final_transcription
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
            
        if "invalid file format" in err_msg or "supported formats" in err_msg:
            return jsonify({'error': 'Formato de audio inválido o archivo corrupto.'}), 400
            
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

# --- Voice Preview (independent from /api/generate) ---
#
# Previews are short, deterministic clips of a FIXED sentence. They never touch
# the textarea, the uploaded file, the audio settings or the main player, and
# they are stored in their own folder (PREVIEW_FOLDER) so they can never be
# confused with, or evict, a user's generated audio.
#
# Caching is content-addressed: the filename is a hash of (voice, text,
# parameters). Generation writes to a temporary file inside the same folder and
# is then moved into place with os.replace(), which is atomic on POSIX and
# Windows, so a concurrent reader either sees no file or a complete file.
#
# RENDER / EPHEMERAL FILESYSTEM: this cache lives on the instance's local disk.
# Render recycles containers on deploy, restart and scaling, so the cache only
# survives as long as the instance does. That is acceptable (a cold preview is
# just one regeneration) and no external storage is introduced.

PREVIEW_FILENAME_RE = re.compile(r'^preview_[0-9a-f]{32}\.mp3$')

# One lock per voice, so two concurrent requests for the same voice generate the
# clip once, while requests for different voices still run in parallel.
_preview_locks = {}
_preview_locks_guard = threading.Lock()


def _get_preview_lock(voice):
    with _preview_locks_guard:
        lock = _preview_locks.get(voice)
        if lock is None:
            lock = threading.Lock()
            _preview_locks[voice] = lock
        return lock


def _preview_filename(voice):
    """Deterministic cache key from voice + fixed text + fixed parameters."""
    digest_source = "|".join([
        voice,
        PREVIEW_TEXT,
        str(PREVIEW_RATE),
        str(PREVIEW_PITCH),
        str(PREVIEW_VOLUME),
    ])
    digest = hashlib.sha256(digest_source.encode('utf-8')).hexdigest()[:32]
    return f"preview_{digest}.mp3"


@app.route('/api/voice-preview', methods=['POST'])
@limiter.limit("20 per minute")
def voice_preview():
    """Generate (or serve from cache) a sample clip for a catalog voice."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Se esperaba un cuerpo JSON con el campo "voice".'}), 400

    voice = payload.get('voice')
    if isinstance(voice, str):
        voice = voice.strip()
    if not voice:
        return jsonify({'error': 'Falta el campo "voice".'}), 400
    if not is_allowed_voice(voice):
        logger.warning(f"Preview rejected for voice outside catalog: {voice!r}")
        return jsonify({'error': 'Voz no disponible.'}), 400

    preview_folder = app.config['PREVIEW_FOLDER']
    os.makedirs(preview_folder, exist_ok=True)

    filename = _preview_filename(voice)
    output_path = os.path.join(preview_folder, filename)

    cached = os.path.exists(output_path)
    if not cached:
        lock = _get_preview_lock(voice)
        with lock:
            # Re-check inside the lock: another request may have finished while
            # we were waiting, and regenerating would be pure waste.
            if os.path.exists(output_path):
                cached = True
            else:
                # Temp name starts with '.' so cleanup_old_files skips it.
                fd, tmp_path = tempfile.mkstemp(
                    dir=preview_folder, prefix='.preview_tmp_', suffix='.mp3'
                )
                os.close(fd)
                try:
                    generate_mp3_sync(
                        PREVIEW_TEXT, voice,
                        PREVIEW_RATE, PREVIEW_PITCH, PREVIEW_VOLUME,
                        tmp_path
                    )
                    os.replace(tmp_path, output_path)
                    logger.info(f"Preview generated for {voice} -> {filename}")
                except Exception as e:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    logger.error(f"Preview generation failed for {voice}: {e}")
                    return jsonify({'error': 'No se pudo generar la muestra de voz.'}), 500

    return jsonify({
        'success': True,
        'voice': voice,
        'cached': cached,
        'audio_url': url_for('get_voice_preview', filename=filename),
    })


@app.route('/api/voice-preview/<filename>', methods=['GET'])
def get_voice_preview(filename):
    """Serve a cached preview clip. Only content-addressed preview names are
    accepted, so this route cannot reach any other file or folder."""
    safe_name = secure_filename(filename)
    if not PREVIEW_FILENAME_RE.match(safe_name):
        return jsonify({'error': 'Muestra no encontrada.'}), 404

    preview_path = os.path.join(app.config['PREVIEW_FOLDER'], safe_name)
    if not os.path.isfile(preview_path):
        return jsonify({'error': 'Muestra no encontrada.'}), 404

    return send_from_directory(app.config['PREVIEW_FOLDER'], safe_name, mimetype='audio/mpeg')

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
