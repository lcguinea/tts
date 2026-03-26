import os
import time
import asyncio
import edge_tts
from striprtf.striprtf import rtf_to_text

def cleanup_old_files(directories, max_age_seconds=3600):
    """
    Deletes files older than max_age_seconds in the given directories.
    Simple and reliable approach without threading complexities.
    """
    now = time.time()
    for directory in directories:
        if not os.path.exists(directory):
            continue
        for filename in os.listdir(directory):
            if filename.startswith('.'):
                continue
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                try:
                    file_stat = os.stat(filepath)
                    if file_stat.st_mtime < now - max_age_seconds:
                        os.remove(filepath)
                except Exception as e:
                    print(f"Error cleaning {filepath}: {e}")

async def _generate_audio(text, voice, rate_str, pitch_str, volume_str, output_path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate_str,
        pitch=pitch_str,
        volume=volume_str
    )
    await communicate.save(output_path)

def generate_mp3_sync(text, voice, rate, pitch, volume, output_path):
    """
    Robust synchronous wrapper for edge-tts asyncio requirements.
    """
    # edge-tts expects strings like "+50%" or "-10Hz"
    # We ensure the sign is always present as some versions/engines are picky
    rate_str = f"{rate:+d}%"
    pitch_str = f"{pitch:+d}Hz"
    volume_str = f"{volume:+d}%"
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Generating MP3: voice={voice}, rate={rate_str}, pitch={pitch_str}, volume={volume_str}")
    
    if not text or not text.strip():
        raise ValueError("Text content is empty")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _generate_audio(text, voice, rate_str, pitch_str, volume_str, output_path)
        )
    except Exception as e:
        logger.error(f"Async generate_audio failed: {str(e)}")
        raise e
    finally:
        loop.close()

def extract_text_from_file(filepath):
    """
    Extracts text from .txt and .rtf files.
    Returns the extracted text or raises ValueError if unsupported.
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    # Try multiple encodings for broader compatibility (RTF can be tricky)
    encodings = ['utf-8', 'latin-1', 'cp1252']
    content = None
    
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
            
    if content is None:
        # Last resort: read with errors='ignore'
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
    if ext == '.rtf':
        try:
            text = rtf_to_text(content)
            if not text or not text.strip():
                # If striprtf returns nothing, maybe it's a structural issue
                return "Error: No se pudo extraer texto del archivo RTF."
            return text
        except Exception as e:
            raise ValueError(f"Error al procesar el formato RTF: {str(e)}")
    elif ext == '.txt':
        return content
    else:
        raise ValueError("Formato de archivo no soportado. Usa .txt o .rtf.")
