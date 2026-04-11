# TTS & STT Webapp (Premium AI Toolbox)

Una WebApp Full-Stack construida en **Python 3.11 + Flask** que ofrece herramientas de voz inteligentes:
- **Texto a Voz (TTS)**: Convierte texto a audio con voces premium usando `edge-tts`.
- **Audio a Texto (STT)**: Transcribe audios subidos o grabados desde el navegador usando la **API oficial de OpenAI**.

## ✨ Características
* **Interfaz Multitarea**: Pestañas con diseño moderno y minimalista (Tailwind CSS + Phosphor Icons).
* **Grabación Integrada**: Graba notas de voz directamente desde el navegador y transcríbelas al instante.
* **Arquitectura Cloud**: Usa la API de OpenAI para transcripción, optimizando el consumo de RAM para planes gratuitos.
* **Seguridad & Rate Limiting**: Protección CSRF, aislamiento de sesiones con UUID y limpieza automática de temporales.
* **Optimizado para Render**: Configuración ligera diseñada para 512MB RAM mediante el uso de APIs externas.

## 🚀 Despliegue en Producción (Render.com)

### Pasos para Desplegar:
1. Sube el proyecto a GitHub.
2. En Render, crea un nuevo **Web Service**.
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `gunicorn --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:$PORT app:app`
5. **Variables de Entorno**:
   - `OPENAI_API_KEY`: Tu clave de API de OpenAI (Obligatorio).
   - `OPENAI_TRANSCRIBE_MODEL`: `gpt-4o-mini-transcribe` (Recomendado por coste y velocidad).
   - `SECRET_KEY`: `(tu_secreto)`
   - `FLASK_ENV`: `production`

> [!IMPORTANT]
> **Estabilidad en Render Free:** Hemos migrado de Whisper local a la API de OpenAI para evitar errores de "Out of Memory" (OOM). Esto garantiza que la app responda siempre de forma rápida y estable.

### 📏 Límites & Costes (OpenAI API)
- **Coste Estimado**: `gpt-4o-mini-transcribe` cuesta aproximadamente $0.30 por cada millón de tokens de audio.
- **Formatos**: `.mp3`, `.wav`, `.m4a`, `.webm`, `.ogg`, `.opus`, `.mp4`.
- **Tamaño máximo**: 10MB (Configurado en `config.py`).

---

## 🛠 Instalación y Prueba Local

### 1. Requisitos Previos
- Python 3.11+
- **FFmpeg instalado** (necesario para el pre-procesamiento de audio).

### 2. Preparar el Entorno
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuración
Crea un archivo `.env` o define las variables:
```bash
OPENAI_API_KEY=tu_clave_aqui
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
```

### 4. Ejecutar
```bash
python app.py
```
Accede a [http://localhost:5000](http://localhost:5000).
