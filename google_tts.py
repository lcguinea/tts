"""
Premium voices through Google Cloud Text-to-Speech (REST v1, API key).

Google bills per character sent, and a single synthesize request accepts at
most 5,000 bytes of input, so long texts are split at sentence boundaries,
synthesized in parallel and the MP3 pieces concatenated in order.
"""
import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger(__name__)

SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# Google's hard limit is 5,000 bytes per request; keep a safety margin.
MAX_CHUNK_BYTES = 4500
MAX_PARALLEL_REQUESTS = 4
REQUEST_TIMEOUT = 90


class GoogleTTSError(Exception):
    """Error with a message that can be shown to the user as is."""

    def __init__(self, user_message, status=502):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def billable_characters(text):
    """Characters Google will bill for this text (it counts every character)."""
    return len(text)


def estimate_cost_usd(text, price_per_million):
    return billable_characters(text) * price_per_million / 1_000_000


def _utf8_len(s):
    return len(s.encode("utf-8"))


def split_text_by_bytes(text, max_bytes=MAX_CHUNK_BYTES):
    """Split text into chunks of at most max_bytes (UTF-8), preferring
    paragraph and sentence boundaries, then spaces, so no word is cut."""
    text = text.strip()
    if _utf8_len(text) <= max_bytes:
        return [text] if text else []

    pieces = re.split(r"(?<=[.!?…;:])\s+|\n+", text)
    chunks, current = [], ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for piece in pieces:
        if not piece or not piece.strip():
            continue
        candidate = f"{current} {piece}".strip() if current else piece
        if _utf8_len(candidate) <= max_bytes:
            current = candidate
            continue
        flush()
        if _utf8_len(piece) <= max_bytes:
            current = piece
            continue
        # A single sentence longer than the limit: cut on spaces.
        for word in piece.split():
            candidate = f"{current} {word}".strip() if current else word
            if _utf8_len(candidate) <= max_bytes:
                current = candidate
            else:
                flush()
                # A single "word" over the limit (very unlikely): hard cut.
                while _utf8_len(word) > max_bytes:
                    cut = max_bytes
                    while _utf8_len(word[:cut]) > max_bytes:
                        cut -= 1
                    chunks.append(word[:cut])
                    word = word[cut:]
                current = word
    flush()
    return chunks


def build_audio_config(voice, rate, pitch, volume):
    """Map the app's sliders to Google's audioConfig.

    rate   -100..100 %  -> speakingRate 0.25..2.0 (1.0 = normal)
    pitch  -20..20 Hz   -> pitch in semitones (half the slider value)
    volume -100..100 %  -> volumeGainDb -6..+6
    Studio and Chirp 3 HD voices reject pitch, so it is only sent to the rest.
    """
    config = {"audioEncoding": "MP3"}
    if rate:
        config["speakingRate"] = round(max(0.25, min(2.0, 1 + rate / 100)), 2)
    if pitch and voice.get("supports_pitch", False):
        config["pitch"] = round(max(-20.0, min(20.0, pitch / 2)), 1)
    if volume:
        config["volumeGainDb"] = round(max(-6.0, min(6.0, volume * 6 / 100)), 1)
    return config


def _google_reason(resp):
    """Short reason from a Google error body, e.g. 'PERMISSION_DENIED (API_KEY_INVALID)'."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        return f"HTTP {resp.status_code}"
    reasons = [d.get("reason") for d in err.get("details", []) if isinstance(d, dict) and d.get("reason")]
    status = err.get("status") or f"HTTP {resp.status_code}"
    return f"{status} ({', '.join(reasons)})" if reasons else f"{status}: {err.get('message', '')[:160]}"


def _synthesize_chunk(text, voice, audio_config, api_key):
    body = {
        "input": {"text": text},
        "voice": {"languageCode": voice["language_code"], "name": voice["id"]},
        "audioConfig": audio_config,
    }
    try:
        resp = requests.post(SYNTHESIZE_URL, params={"key": api_key}, json=body,
                             timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"Google TTS network error: {e}")
        raise GoogleTTSError("No he podido conectar con Google. Prueba otra vez en unos segundos.", 503)

    if resp.status_code == 400 and len(audio_config) > 1:
        # Some voice families reject speakingRate/pitch/volumeGainDb: retry plain.
        logger.warning(f"Google TTS rejected audioConfig {audio_config} for {voice['id']}: "
                       f"{resp.text[:300]}. Retrying without adjustments.")
        return _synthesize_chunk(text, voice, {"audioEncoding": "MP3"}, api_key)

    if resp.status_code != 200:
        detail = resp.text[:500]
        logger.error(f"Google TTS HTTP {resp.status_code} for {voice['id']}: {detail}")
        reason = _google_reason(resp)
        if resp.status_code in (401, 403):
            if "API_KEY_SERVICE_BLOCKED" in detail or "are blocked" in detail:
                raise GoogleTTSError("Tu clave de Google no tiene permiso para Text-to-Speech (está restringida a otras APIs, p. ej. Gemini). "
                                     "Añade «Cloud Text-to-Speech API» a sus restricciones o crea una clave nueva.", 502)
            if "SERVICE_DISABLED" in detail or "has not been used" in detail:
                raise GoogleTTSError("La API de Text-to-Speech no está activada en tu proyecto de Google Cloud.", 502)
            if "BILLING" in detail.upper():
                raise GoogleTTSError("Tu proyecto de Google Cloud no tiene la facturación activada.", 502)
            raise GoogleTTSError(f"Google ha rechazado la clave (GOOGLE_API_KEY): {reason}", 502)
        if resp.status_code == 429:
            raise GoogleTTSError("Google ha limitado las peticiones. Espera un minuto y vuelve a probar.", 429)
        if resp.status_code == 400:
            raise GoogleTTSError("Google no acepta este texto o esta voz. Prueba con otra voz premium.", 400)
        raise GoogleTTSError("Google no ha podido generar el audio. Prueba otra vez en un momento.", 502)

    content = resp.json().get("audioContent")
    if not content:
        raise GoogleTTSError("Google no devolvió audio para este texto.", 502)
    return base64.b64decode(content)


def synthesize_to_mp3(text, voice, rate, pitch, volume, output_path, api_key):
    """Synthesize text with a Google voice entry from voices.py into output_path.
    Returns the number of billed characters."""
    if not api_key:
        raise GoogleTTSError("Las voces premium no están configuradas (falta GOOGLE_API_KEY).", 503)
    chunks = split_text_by_bytes(text)
    if not chunks:
        raise GoogleTTSError("El texto está vacío.", 400)
    audio_config = build_audio_config(voice, rate, pitch, volume)
    logger.info(f"Google TTS: voice={voice['id']} chunks={len(chunks)} chars={len(text)} config={audio_config}")

    if len(chunks) == 1:
        parts = [_synthesize_chunk(chunks[0], voice, audio_config, api_key)]
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_REQUESTS, len(chunks))) as pool:
            parts = list(pool.map(lambda c: _synthesize_chunk(c, voice, audio_config, api_key), chunks))

    # Google's MP3 output is a plain MPEG stream: pieces concatenate cleanly.
    with open(output_path, "wb") as f:
        for part in parts:
            f.write(part)
    return sum(billable_characters(c) for c in chunks)
