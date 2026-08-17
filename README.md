# TTS & STT Webapp (Premium AI Toolbox)

Una WebApp Full-Stack construida en **Python 3.11 + Flask** que ofrece herramientas de voz inteligentes:
- **Texto a Voz (TTS)**: Convierte texto a audio con voces premium usando `edge-tts`.
- **Audio a Texto (STT)**: Transcribe audios subidos o grabados desde el navegador usando la **API oficial de OpenAI**.

## ✨ Características
* **Interfaz Multitarea**: Pestañas con diseño moderno y minimalista (Tailwind CSS + Phosphor Icons).
* **Grabación Integrada**: Graba notas de voz directamente desde el navegador y transcríbelas al instante.
* **Muestra de voz**: Botón «Escuchar muestra» que reproduce una frase fija con la voz seleccionada, sin tocar tu texto ni el reproductor principal.
* **Arquitectura Cloud**: Usa la API de OpenAI para transcripción, optimizando el consumo de RAM para planes gratuitos.
* **Seguridad & Rate Limiting**: Protección CSRF, aislamiento de sesiones con UUID y limpieza automática de temporales.
* **Optimizado para Render**: Configuración ligera diseñada para 512MB RAM mediante el uso de APIs externas.

---

## 🔊 Catálogo de voces y muestra de voz (preview)

### Arquitectura

| Pieza | Responsabilidad |
|---|---|
| `voices.py` | **Catálogo único**. Grupos (España / México / Latinoamérica), bandera, nombre amigable, texto fijo de la muestra y parámetros de la muestra. Es la única fuente de verdad. |
| `config.py` | `PREVIEW_FOLDER` (carpeta de caché separada de `GENERATED_FOLDER`) y `PREVIEW_MAX_AGE_SECONDS`. |
| `app.py` → `POST /api/voice-preview` | Genera o devuelve desde caché la muestra. Protegido por CSRF y limitado a 20 peticiones/minuto. |
| `app.py` → `GET /api/voice-preview/<filename>` | Sirve el MP3 cacheado. Solo acepta nombres con el patrón `preview_<32 hex>.mp3`. |
| `templates/index.html` | Renderiza el `<select>` con `<optgroup>` a partir del catálogo, el botón «Escuchar muestra», su estado/error propio y un `<audio>` de preview independiente. |
| `static/js/app.js` | Petición JSON con `X-CSRFToken`, estado de carga, bloqueo de clics simultáneos y descarte de respuestas obsoletas. |

Decisiones relevantes:

* **No reutiliza `/api/generate`.** Son dos endpoints, dos carpetas y dos elementos `<audio>` distintos.
* **El preview solo lee el valor del `<select>`.** Nunca lee, envía ni modifica el textarea, el archivo subido, los ajustes de velocidad/tono/volumen ni el reproductor principal. El texto es siempre y exclusivamente:
  `«Hola. Esta es una muestra de mi voz. Espero que te guste cómo sueno.»`
* **Caché determinista.** El nombre del fichero es `preview_<sha256(voz|texto|rate|pitch|volume)[:32]>.mp3`, así que la misma voz siempre reutiliza el mismo fichero y cualquier cambio futuro del texto o de los parámetros lo invalida solo.
* **Escritura atómica.** Se escribe en un temporal dentro de la misma carpeta y se mueve con `os.replace()`, de modo que un lector concurrente ve el fichero completo o no lo ve.
* **Sincronización por voz.** Un `threading.Lock` por voz evita generar dos veces la misma muestra en peticiones simultáneas; dentro del bloqueo se vuelve a comprobar si el fichero ya existe. Voces distintas siguen generándose en paralelo.
* **Limpieza.** La caché entra en la limpieza periódica con una antigüedad de 24 h (`PREVIEW_MAX_AGE_SECONDS`), frente a 1 h de los audios normales y las subidas.

> [!IMPORTANT]
> **Render usa filesystem efímero.** La caché de muestras vive en el disco local de la instancia (`/tmp`). Render reemplaza el contenedor en cada despliegue, reinicio o evento de escalado, así que **la caché solo dura mientras vive la instancia**. Tras un reinicio, la primera muestra de cada voz se regenera. Es intencional: no se añade ningún almacenamiento externo.

### Voces disponibles

Catálogo único (`voices.py`), del que leen la plantilla, `/api/generate` y `/api/voice-preview`:

| Grupo | Voces |
|---|---|
| 🇪🇸 España | `es-ES-AlvaroNeural`, `es-ES-ElviraNeural` |
| 🇲🇽 México | `es-MX-DaliaNeural`, `es-MX-JorgeNeural` |
| 🌎 Latinoamérica | `es-AR-TomasNeural`, `es-CO-GonzaloNeural`, `es-US-AlonsoNeural` |

**Catálogo mexicano (verificación completada).** Se ejecutó `edge_tts.list_voices()` con el venv real del proyecto y salida a Internet:

```bash
python -c "import asyncio, edge_tts; print(sorted(v['ShortName'] for v in asyncio.run(edge_tts.list_voices()) if v['Locale'] == 'es-MX'))"
```

Microsoft ofrece exactamente dos voces es-MX, y ambas están en el catálogo:

| Voz | Género | Etiqueta visible | Estado |
|---|---|---|---|
| `es-MX-DaliaNeural` | Female — Microsoft Dalia Online (Natural) - Spanish (Mexico) | 🇲🇽 Dalia (México) | **Incluida.** |
| `es-MX-JorgeNeural` | Male — Microsoft Jorge Online (Natural) - Spanish (Mexico) | 🇲🇽 Jorge (México) | **Incluida.** Ya estaba en uso y se conserva. |

`es-MX-CecilioNeural` y `es-MX-BeatrizNeural` **quedan descartadas por validación real**: no aparecieron en la salida de `edge_tts.list_voices()` para el locale `es-MX`, y por eso no deben añadirse ni se ofrecen ni se aceptan (`DISCARDED_VOICES` en `voices.py`). No hay ninguna voz pendiente de verificar.

### Validación manual realizada

Además de las pruebas automatizadas (que simulan Edge TTS), la muestra de voz se comprobó a mano contra Edge TTS real:

- **🇲🇽 Jorge (`es-MX-JorgeNeural`)** — muestra reproducida correctamente.
- **🇲🇽 Dalia (`es-MX-DaliaNeural`)** — muestra reproducida correctamente.

En esas comprobaciones se observó el flujo completo esperado: aparece el indicador de carga, el frontend hace **un único POST** a `/api/voice-preview`, a continuación solicita el MP3 mediante `GET /api/voice-preview/<filename>`, y el audio se reproduce.

El catálogo mexicano se validó consultando Edge TTS real con `edge_tts.list_voices()`: confirma las dos voces es-MX (Dalia y Jorge), y `es-MX-CecilioNeural` y `es-MX-BeatrizNeural` no aparecen en esa consulta.

No se han realizado comprobaciones específicas por navegador o dispositivo (Chrome, Safari, iPhone); el comportamiento del autoplay en cada navegador queda fuera de lo verificado.

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

### 5. Pruebas

Las pruebas de la muestra de voz no necesitan red ni runner externo: simulan Edge TTS.

```bash
python tests/test_voice_preview.py
```

Cubren: voz válida, voz arbitraria rechazada con 400, CSRF obligatorio, texto y parámetros fijos, segunda petición servida desde caché, carrera concurrente sin generación duplicada, y separación entre la caché de muestras y los audios normales. Al terminar imprimen `voice preview tests passed`.

### 6. Probar la muestra de voz a mano (local)

1. Arranca `python app.py` y abre la página.
2. En «Voz», elige una entrada del selector (agrupado en España / México / Latinoamérica).
3. Pulsa **Escuchar muestra**. La primera vez tarda lo que tarde Edge TTS; las siguientes son instantáneas (caché).
4. Cambia de voz y vuelve a pulsar: no debe sonar la muestra anterior.
5. Comprueba que el textarea, el archivo, los sliders y el reproductor principal quedan intactos.
