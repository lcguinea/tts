"""
Premium voices through Gemini TTS (Gemini API, Google AI Studio key).

Gemini bills tokens: the text you send (input) and the audio it returns
(output, 25 tokens per second of audio). The audio length is only known after
generating, so quotes are estimates and the real cost is computed afterwards
from the usage the API reports (or from the audio duration).

Audio comes back as 16-bit mono PCM at 24 kHz (raw or inside a WAV header);
it is encoded to MP3 with lameenc (pure wheel, no system packages). Speed is
applied with ffmpeg's atempo when ffmpeg exists; volume is applied in Python.
"""
import array
import base64
import datetime
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import lameenc
import requests

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
FALLBACK_MODEL = "gemini-2.5-flash-preview-tts"

# USD per 1M tokens, paid tier, from https://ai.google.dev/gemini-api/docs/pricing
# (read 21-11-2026). Gemini 3.8 TTS prices double from 1 Jan 2027.
PRICING = {
    "gemini-3.8-flash-tts": [
        {"until": datetime.date(2026, 12, 31), "input": 0.50, "output": 9.00},
        {"until": None, "input": 1.00, "output": 18.00},
    ],
    "gemini-3.8-flash-lite-tts": [
        {"until": datetime.date(2026, 12, 31), "input": 0.50, "output": 6.00},
        {"until": None, "input": 1.00, "output": 12.00},
    ],
    "gemini-2.5-flash-preview-tts": [{"until": None, "input": 0.50, "output": 10.00}],
}
AUDIO_TOKENS_PER_SECOND = 25
# Estimation only: Spanish read aloud runs at roughly 14-16 characters per
# second; 14 errs on the side of a slightly higher quote.
CHARS_PER_SECOND = 14
CHARS_PER_INPUT_TOKEN = 4

SAMPLE_RATE = 24000
# The model accepts 8,192 input tokens and returns at most 16,384 audio tokens
# (~11 minutes). 2,500 characters is ~3 minutes of audio: well inside both.
MAX_CHUNK_CHARS = 2500
MAX_PARALLEL_REQUESTS = 3
REQUEST_TIMEOUT = 180


class GeminiTTSError(Exception):
    """Error with a message that can be shown to the user as is."""

    def __init__(self, user_message, status=502):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def prices_for(model, today=None):
    today = today or datetime.date.today()
    for tier in PRICING.get(model, PRICING[DEFAULT_MODEL]):
        if tier["until"] is None or today <= tier["until"]:
            return tier
    return PRICING[DEFAULT_MODEL][-1]


def cost_usd(model, input_tokens, output_tokens):
    p = prices_for(model)
    return input_tokens * p["input"] / 1e6 + output_tokens * p["output"] / 1e6


def estimate(text, model):
    """Quote before generating: estimated seconds of audio, tokens and cost."""
    chars = len(text)
    seconds = chars / CHARS_PER_SECOND
    in_tok = max(1, round(chars / CHARS_PER_INPUT_TOKEN))
    out_tok = round(seconds * AUDIO_TOKENS_PER_SECOND)
    p = prices_for(model)
    return {
        "chars": chars,
        "seconds": round(seconds),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "price_input_per_million": p["input"],
        "price_output_per_million": p["output"],
        "cost_usd": round(cost_usd(model, in_tok, out_tok), 6),
    }


def split_text(text, max_chars=MAX_CHUNK_CHARS):
    """Chunks of at most max_chars, cut at paragraph/sentence ends, then spaces."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    pieces = re.split(r"(?<=[.!?…;:])\s+|\n+", text)
    chunks, current = [], ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        candidate = f"{current} {piece}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = ""
        while len(piece) > max_chars:
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        current = piece
    if current:
        chunks.append(current)
    return chunks


def _pcm_from_payload(data):
    raw = base64.b64decode(data)
    if raw[:4] == b"RIFF":
        # WAV: find the 'data' chunk and return only the samples.
        idx = raw.find(b"data")
        if idx != -1:
            return raw[idx + 8:]
    return raw


def _call(text, voice_name, model, api_key, attempt=0):
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
        },
    }
    try:
        resp = requests.post(API_URL.format(model=model), headers={"x-goog-api-key": api_key},
                             json=body, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"Gemini TTS network error: {e}")
        raise GeminiTTSError("No he podido conectar con Gemini. Prueba otra vez en unos segundos.", 503)

    if resp.status_code == 429 and attempt < 2:
        wait = 8 * (attempt + 1)
        logger.warning(f"Gemini TTS 429, retrying in {wait}s")
        time.sleep(wait)
        return _call(text, voice_name, model, api_key, attempt + 1)

    if resp.status_code != 200:
        detail = resp.text[:600]
        logger.error(f"Gemini TTS HTTP {resp.status_code} model={model}: {detail}")
        if resp.status_code == 404:
            raise GeminiTTSError(f"model-not-found:{model}", 404)
        if resp.status_code in (401, 403) or "API_KEY_INVALID" in detail:
            raise GeminiTTSError("Gemini ha rechazado la clave (GOOGLE_API_KEY). Revisa que sea una clave válida de Google AI Studio.", 502)
        if resp.status_code == 429:
            raise GeminiTTSError("Has llegado al límite de uso de Gemini (por minuto o por día). Espera un poco y vuelve a probar.", 429)
        if resp.status_code == 400:
            raise GeminiTTSError("Gemini no ha aceptado este texto. Prueba a acortarlo o con otra voz.", 400)
        raise GeminiTTSError("Gemini no ha podido generar el audio. Prueba otra vez en un momento.", 502)

    payload = resp.json()
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        data = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
    except (KeyError, IndexError, StopIteration):
        logger.error(f"Gemini TTS: no audio in response: {str(payload)[:400]}")
        raise GeminiTTSError("Gemini no devolvió audio para este texto.", 502)
    pcm = _pcm_from_payload(data)
    usage = payload.get("usageMetadata", {})
    seconds = len(pcm) / (SAMPLE_RATE * 2)
    in_tok = usage.get("promptTokenCount") or max(1, round(len(text) / CHARS_PER_INPUT_TOKEN))
    out_tok = usage.get("candidatesTokenCount") or round(seconds * AUDIO_TOKENS_PER_SECOND)
    return pcm, in_tok, out_tok


def _apply_volume(pcm, volume):
    if not volume:
        return pcm
    factor = 10 ** ((volume * 6 / 100) / 20)  # -100..100 % -> -6..+6 dB
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    for i, s in enumerate(samples):
        samples[i] = max(-32768, min(32767, int(s * factor)))
    return samples.tobytes()


def _apply_speed(pcm, rate):
    """rate -100..100 % -> atempo 0.5..2.0 via ffmpeg, if available."""
    if not rate or not shutil.which("ffmpeg"):
        if rate:
            logger.warning("ffmpeg not found: speed change skipped for Gemini voice.")
        return pcm
    tempo = max(0.5, min(2.0, 1 + rate / 100))
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.pcm"), os.path.join(d, "out.pcm")
        with open(src, "wb") as f:
            f.write(pcm)
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", src,
                            "-filter:a", f"atempo={tempo}", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", dst],
                           capture_output=True, check=True, timeout=120)
            with open(dst, "rb") as f:
                return f.read()
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"ffmpeg atempo failed, keeping original speed: {e}")
            return pcm


def _encode_mp3(pcm, output_path):
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(SAMPLE_RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    with open(output_path, "wb") as f:
        f.write(enc.encode(pcm))
        f.write(enc.flush())


def synthesize_to_mp3(text, voice, rate, volume, output_path, api_key, model=DEFAULT_MODEL):
    """Generate text with a Gemini voice into an MP3. Returns a usage dict with
    the real tokens, seconds, cost and the model actually used."""
    if not api_key:
        raise GeminiTTSError("Las voces premium no están configuradas (falta GOOGLE_API_KEY).", 503)
    chunks = split_text(text)
    if not chunks:
        raise GeminiTTSError("El texto está vacío.", 400)

    def run(m):
        if len(chunks) == 1:
            return [_call(chunks[0], voice["voice_name"], m, api_key)]
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_REQUESTS, len(chunks))) as pool:
            return list(pool.map(lambda c: _call(c, voice["voice_name"], m, api_key), chunks))

    used_model = model
    try:
        results = run(model)
    except GeminiTTSError as e:
        if e.status == 404 and model != FALLBACK_MODEL:
            logger.warning(f"Gemini model {model} not available, falling back to {FALLBACK_MODEL}")
            used_model = FALLBACK_MODEL
            try:
                results = run(FALLBACK_MODEL)
            except GeminiTTSError as e2:
                if e2.status == 404:
                    raise GeminiTTSError("Los modelos de voz de Gemini no están disponibles para tu clave.", 502)
                raise
        else:
            raise
    pcm = b"".join(r[0] for r in results)
    in_tok = sum(r[1] for r in results)
    out_tok = sum(r[2] for r in results)
    seconds = len(pcm) / (SAMPLE_RATE * 2)
    pcm = _apply_speed(_apply_volume(pcm, volume), rate)
    _encode_mp3(pcm, output_path)
    usage = {
        "model": used_model,
        "chunks": len(chunks),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "seconds": round(seconds, 1),
        "cost_usd": round(cost_usd(used_model, in_tok, out_tok), 6),
    }
    logger.info(f"Gemini TTS done: voice={voice['voice_name']} {usage}")
    return usage
