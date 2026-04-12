import os
import time
import asyncio
import edge_tts
import subprocess
import json
import logging
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

def get_audio_duration(filepath):
    """
    Get the duration of an audio/video file in seconds using ffprobe or ffmpeg.
    """
    logger = logging.getLogger(__name__)
    try:
        # Try ffprobe first (more direct)
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        # Fallback to ffmpeg -i if ffprobe is missing or fails
        try:
            cmd = ['ffmpeg', '-i', filepath]
            result = subprocess.run(cmd, capture_output=True, text=True)
            # Ffmpeg sends info to stderr when no output file is specified
            output = result.stderr
            import re
            match = re.search(r"Duration:\s(\d+):(\d+):(\d+\.\d+)", output)
            if match:
                hours, mins, secs = match.groups()
                return int(hours) * 3600 + int(mins) * 60 + float(secs)
        except Exception as e:
            logger.error(f"Failed to get audio duration: {str(e)}")
    
    return 0.0

def split_audio_ffmpeg(filepath, output_dir, chunk_duration=300, overlap=5):
    """
    Splits an audio file into chunks with overlap using ffmpeg.
    Returns a list of chunk file paths.
    """
    logger = logging.getLogger(__name__)
    duration = get_audio_duration(filepath)
    if duration <= 0:
        logger.warning(f"Could not determine duration for {filepath}, proceeding without splitting.")
        return [filepath]

    # If it's shorter than chunk_duration + bit of margin, don't split
    if duration <= chunk_duration + overlap:
        return [filepath]

    chunks = []
    base_name = os.path.basename(filepath)
    name_no_ext, ext = os.path.splitext(base_name)
    
    # Ensure extension is something ffmpeg can write easily for chunks (use .mp3 or original if supported)
    # Most formats we support (.opus, .m4a, etc) ffmpeg handles well.
    chunk_ext = ext if ext in ['.mp3', '.wav', '.m4a'] else '.mp3'

    start_time = 0
    chunk_idx = 0
    
    while start_time < duration:
        chunk_filename = f"{name_no_ext}_chunk_{chunk_idx}{chunk_ext}"
        chunk_path = os.path.join(output_dir, chunk_filename)
        
        # Calculate actual duration for this chunk (chunk_duration + overlap)
        # except for the last one
        current_t = chunk_duration + overlap
        
        # ffmpeg -ss [start] -t [duration] -i [input] [output]
        # Using -ss before -i is faster (input seeking)
        cmd = [
            'ffmpeg', '-y', '-ss', str(start_time), '-t', str(current_t),
            '-i', filepath, '-c', 'copy', chunk_path
        ]
        
        # If 'copy' fails (e.g. seeking into non-keyframes or format issues), try re-encoding
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            # Re-encode as fallback
            cmd = [
                'ffmpeg', '-y', '-ss', str(start_time), '-t', str(current_t),
                '-i', filepath, '-q:a', '2', chunk_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        chunks.append(chunk_path)
        
        # Advance start_time by chunk_duration (the overlap stays for the NEXT chunk)
        start_time += chunk_duration
        chunk_idx += 1
        
        # Small safety break
        if start_time >= duration - overlap:
            break

    logger.info(f"Split {filepath} into {len(chunks)} chunks.")
    return chunks

def deduplicate_text(text_a, text_b, max_overlap_words=20):
    """
    Very simple deduplication at the boundary of two texts.
    Looks for a sequence of words from the end of text_a at the beginning of text_b.
    """
    if not text_a or not text_b:
        return text_b
        
    words_a = text_a.split()
    words_b = text_b.split()
    
    if not words_a or not words_b:
        return text_b
        
    # We look for the last 'size' words of A at the very beginning of B
    # We iterate backwards from max_overlap_words to find the longest possible match
    for size in range(min(len(words_a), len(words_b), max_overlap_words), 2, -1):
        tail_a = " ".join(words_a[-size:]).lower().strip('.,!?;:')
        head_b = " ".join(words_b[:size]).lower().strip('.,!?;:')
        
        if tail_a == head_b:
            # Match found! Return everything from B minus the overlapped words
            return " ".join(words_b[size:])
            
    return text_b
