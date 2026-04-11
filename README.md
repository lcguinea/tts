# TTS & STT Webapp (Premium AI Toolbox)

Una WebApp Full-Stack construida en **Python 3.11 + Flask** que ofrece herramientas de voz inteligentes:
- **Texto a Voz (TTS)**: Convierte texto a audio con voces premium usando `edge-tts`.
- **Audio a Texto (STT)**: Transcribe audios subidos o grabados desde el navegador usando **OpenAI Whisper**.

## ✨ Características
* **Interfaz Multitarea**: Pestañas con diseño moderno y minimalista (Tailwind CSS + Phosphor Icons).
* **Grabación Integrada**: Graba notas de voz directamente desde el navegador y transcríbelas al instante.
* **IA Desplegable**: Usa Whisper "tiny" por defecto para máxima compatibilidad con tiers gratuitos (Render Free).
* **Seguridad & Rate Limiting**: Protección CSRF, aislamiento de sesiones con UUID y limpieza automática de temporales.
* **Optimizado para Render**: Configuración de memoria y workers ajustada para 512MB RAM.

## 🚀 Despliegue en Producción (Render.com)

Render es la opción recomendada. El plan **Free** es suficiente para el modelo "tiny".

### Pasos para Desplegar:
1. Sube el proyecto a GitHub.
2. En Render, crea un nuevo **Web Service**.
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `gunicorn --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:$PORT app:app`
5. **Variables de Entorno**:
   - `WHISPER_MODEL`: `tiny` (Recomendado para Render Free. Ocupa ~150MB RAM).
   - `SECRET_KEY`: `(tu_secreto)`
   - `FLASK_ENV`: `production`

> [!IMPORTANT]
> **Confirmación de FFmpeg:** En Render (entorno Native Python), FFmpeg ya está disponible por defecto. Si usas el **Dockerfile** incluido, la instalación ya está configurada automáticamente.

### 📏 Límites Prácticos (Render Free)
- **Formatos Soportados**: `.mp3`, `.wav`, `.m4a`, `.webm`, `.ogg`, `.opus`, `.mp4` (Video con audio).
- **Conversión Inteligente**: Gracias a `ffmpeg`, la aplicación extrae y normaliza el audio de archivos de video o formatos comprimidos automáticamente antes de transcribir.
- **Tamaño máximo**: 10MB (Configurado en `config.py`).
- **Duración recomendada**: Audios de menos de 5 minutos.
- **Tiempo de espera**: Hemos configurado un timeout de **180 segundos** para evitar cortes.

---

## 🛠 Instalación y Prueba Local

### 1. Requisitos Previos
- Python 3.11+
- **FFmpeg instalado en el sistema** (Obligatorio para transcripción).
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
  - Windows: [Descargar FFmpeg](https://ffmpeg.org/download.html) y añadir al PATH.

### 2. Preparar el Entorno
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuración
Crea un archivo `.env` o define la variable:
`export WHISPER_MODEL=base` (puedes usar `tiny`, `base`, `small`).

### 4. Ejecutar
```bash
python app.py
```
Accede a [http://localhost:5000](http://localhost:5000).

---

## ⚠️ Notas sobre Whisper y Render Free
El modelo `tiny` consume unos ~150-200MB de RAM. El modelo `base` consume ~400-500MB. En el plan gratuito de Render (512MB), el modelo `base` puede provocar reinicios por falta de memoria (OOM). Se recomienda encarecidamente usar `tiny` en producción gratuita.
