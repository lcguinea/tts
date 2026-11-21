"""
Catálogo único de voces compartido por la generación de audio (/api/generate),
la previsualización de voz (/api/voice-preview) y la plantilla `index.html`.

Ningún otro módulo debe declarar su propia lista de voces: si una voz no está
aquí, la aplicación la rechaza.

--------------------------------------------------------------------------
VERIFICACIÓN DE VOCES CANDIDATAS (es-MX) — COMPLETADA
--------------------------------------------------------------------------
Validación real ejecutada con el venv del proyecto y salida a Internet:

    python -c "import asyncio, edge_tts; \
      print(sorted(v['ShortName'] for v in \
      asyncio.run(edge_tts.list_voices()) if v['Locale'] == 'es-MX'))"

`edge_tts.list_voices()` devolvió exactamente dos voces para el locale es-MX:

  * es-MX-DaliaNeural — Female — Microsoft Dalia Online (Natural) - Spanish
    (Mexico)  -> INCLUIDA en el catálogo.
  * es-MX-JorgeNeural — Male — Microsoft Jorge Online (Natural) - Spanish
    (Mexico)  -> INCLUIDA en el catálogo (ya estaba en uso y se conserva).

es-MX-CecilioNeural y es-MX-BeatrizNeural NO aparecieron en la salida de
edge_tts.list_voices() para el locale es-MX, y por eso quedan DESCARTADAS y no
deben añadirse. Ya no son candidatas pendientes.
"""

# Texto fijo e invariable de la muestra de voz. No se acepta texto del usuario.
PREVIEW_TEXT = "Hola. Esta es una muestra de mi voz. Espero que te guste cómo sueno."

# Parámetros fijos de la muestra. Entran en el hash de la caché para que un
# cambio futuro en cualquiera de ellos invalide los ficheros ya generados.
PREVIEW_RATE = 0
PREVIEW_PITCH = 0
PREVIEW_VOLUME = 0

DEFAULT_VOICE = "es-ES-AlvaroNeural"

# Grupos en el orden en que se muestran en el selector.
VOICE_GROUPS = [
    {
        "id": "es-ES",
        "label": "España",
        "flag": "🇪🇸",
        "voices": [
            {
                "id": "es-ES-AlvaroNeural",
                "name": "Álvaro",
                "country": "España",
                "flag": "🇪🇸",
                "gender": "masculina",
            },
            {
                "id": "es-ES-ElviraNeural",
                "name": "Elvira",
                "country": "España",
                "flag": "🇪🇸",
                "gender": "femenina",
            },
        ],
    },
    {
        "id": "es-MX",
        "label": "México",
        "flag": "🇲🇽",
        "voices": [
            {
                "id": "es-MX-DaliaNeural",
                "name": "Dalia",
                "country": "México",
                "flag": "🇲🇽",
                "gender": "femenina",
            },
            {
                "id": "es-MX-JorgeNeural",
                "name": "Jorge",
                "country": "México",
                "flag": "🇲🇽",
                "gender": "masculina",
            },
        ],
    },
    {
        "id": "latam",
        "label": "Latinoamérica",
        "flag": "🌎",
        "voices": [
            {
                "id": "es-AR-TomasNeural",
                "name": "Tomás",
                "country": "Argentina",
                "flag": "🇦🇷",
                "gender": "masculina",
            },
            {
                "id": "es-CO-GonzaloNeural",
                "name": "Gonzalo",
                "country": "Colombia",
                "flag": "🇨🇴",
                "gender": "masculina",
            },
            {
                "id": "es-US-AlonsoNeural",
                "name": "Alonso",
                "country": "Estados Unidos",
                "flag": "🇺🇸",
                "gender": "masculina",
            },
        ],
    },
]

# --------------------------------------------------------------------------
# Voces PREMIUM (Gemini TTS con la clave de Google AI Studio, con coste)
# --------------------------------------------------------------------------
# Gemini detecta el idioma solo: con texto en español, hablan español.
# Precios y modelo en gemini_tts.py (PRICING, DEFAULT_MODEL).
import os as _os
import gemini_tts as _gemini

GEMINI_MODEL = _os.environ.get("GEMINI_TTS_MODEL", _gemini.DEFAULT_MODEL)
# Coste estimado por millón de caracteres, solo para la pista del selector.
GEMINI_PRICE_PER_MILLION_CHARS = round(_gemini.estimate("x" * 1_000_000, GEMINI_MODEL)["cost_usd"], 1)


def _gemini_voice(voice_name, descriptor, gender):
    return {
        "id": f"gemini-{voice_name}",
        "name": voice_name,
        "descriptor": descriptor,
        "country": "Gemini",
        "flag": "⭐",
        "gender": gender,
        "provider": "gemini",
        "voice_name": voice_name,
        "tier_name": "Gemini TTS",
        "price_per_million": GEMINI_PRICE_PER_MILLION_CHARS,
    }


PREMIUM_VOICE_GROUPS = [
    {
        "id": "premium-gemini",
        "label": f"Premium · Gemini (con coste, ≈ {GEMINI_PRICE_PER_MILLION_CHARS:g} $ por millón de caracteres)",
        "flag": "⭐",
        "premium": True,
        "voices": [
            _gemini_voice("Sulafat", "cálida", "femenina"),
            _gemini_voice("Kore", "firme", "femenina"),
            _gemini_voice("Aoede", "desenfadada", "femenina"),
            _gemini_voice("Leda", "juvenil", "femenina"),
            _gemini_voice("Achird", "cercana", "masculina"),
            _gemini_voice("Charon", "informativa", "masculina"),
            _gemini_voice("Puck", "alegre", "masculina"),
            _gemini_voice("Algenib", "grave", "masculina"),
        ],
    },
]

VOICE_GROUPS.extend(PREMIUM_VOICE_GROUPS)

# Ya no hay voces pendientes de verificación: la validación real contra
# `edge_tts.list_voices()` está hecha (véase la cabecera del módulo).
PENDING_VOICES = []

# Candidatas descartadas porque la validación real demostró que no existen en
# el catálogo de edge-tts. Se documentan para que no vuelvan a proponerse.
DISCARDED_VOICES = [
    {"id": "es-MX-CecilioNeural", "reason": "no aparece en edge_tts.list_voices() para es-MX"},
    {"id": "es-MX-BeatrizNeural", "reason": "no aparece en edge_tts.list_voices() para es-MX"},
]


def _build_label(group, voice):
    """Etiqueta visible: bandera + nombre amigable (+ país si el grupo agrupa
    varios países o si el país forma parte del formato acordado). Nunca
    contiene el identificador técnico de la voz."""
    if voice.get("provider") == "gemini":
        return "{flag} {name} · {descriptor} · {gender}".format(**voice)
    if group["id"] == "latam":
        return "{flag} {name} · {country}".format(**voice)
    if group["id"] == "es-MX":
        return "{flag} {name} ({country})".format(**voice)
    return "{flag} {name}".format(**voice)


for _group in VOICE_GROUPS:
    for _voice in _group["voices"]:
        _voice.setdefault("provider", "edge")
        _voice.setdefault("price_per_million", 0.0)
        _voice["label"] = _build_label(_group, _voice)

ALL_VOICES = [voice for group in VOICE_GROUPS for voice in group["voices"]]

ALLOWED_VOICE_IDS = frozenset(voice["id"] for voice in ALL_VOICES)

VOICES_BY_ID = {voice["id"]: voice for voice in ALL_VOICES}


def is_premium(voice_id):
    voice = VOICES_BY_ID.get(voice_id)
    return bool(voice and voice["provider"] == "gemini")


def is_allowed(voice_id):
    """True solo si `voice_id` es exactamente un ID del catálogo."""
    return isinstance(voice_id, str) and voice_id in ALLOWED_VOICE_IDS
