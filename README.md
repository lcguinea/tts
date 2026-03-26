# TTS Webapp (Cost-Zero MVP)

Una WebApp Full-Stack construida en **Python 3.11 + Flask** que convierte texto a audio MP3 utilizando `edge-tts`. Diseñada específicamente para ser desplegada como pública a coste 0.

## ✨ Características de esta versión
* **Texto a Voz (TTS) ilimitado en funcionalidad**: Múltiples voces y configuraciones. Interfaz con prioridad a textarea.
* **Reproductor MVP Custom**: Audio timeline arrastrable, botones interactivos.
* **Seguridad & Rate Limiting**: Protección CSRF, isolation de sesiones UUID con limpieza automática.
* **Diseñado para PaaS Efímero**: Uso de `/tmp` del sistema para evitar problemas de permisos de disco, sin depender de almacenamientos persistentes de pago (como S3).
* **Mínima demanda RAM**: Configuración Gunicorn (`1 worker`, `4 threads`) optimizada para tiers gratuitos de 512MB RAM.

---

## 🚀 Despliegue en Producción a Coste 0 (Recomendado: Render.com)

He elegido **Render** (Free Web Services) como la mejor opción de despliegue principal ya que **no requiere introducir tarjeta de crédito** para proyectos web simples, y ofrece 512MB de RAM, lo cual es generoso para nuestro entorno Gunicorn.

### Pasos para Desplegar Gratis en Render:
1. Sube este proyecto a tu propio repositorio de GitHub, GitLab o Bitbucket.
2. Inicia sesión en [Render.com](https://render.com) y haz clic en **New +** -> **Web Service**.
3. Conecta tu cuenta de GitHub y selecciona el repositorio de este proyecto.
4. Rellena la configuración básica:
   - **Name**: `tu-tts-webapp`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app` (o simplemente puedes dejarlo en blanco o poner `gunicorn app:app`, Render lee el `Procfile` automáticamente).
   - **Instance Type**: Selecciona **Free**.
5. Ve abajo a **Advanced** e inserta las variables de entorno (*Environment Variables*):
   - `FLASK_ENV`: `production`
   - `SECRET_KEY`: `(inventa una string larga alfanumérica secreta)`
6. Clic en **Create Web Service**. Espera ~2-3 minutos a que termine la build e instale las dependencias.
7. ¡Listo! Tu app pública estará accesible en la URL que Render te provee (ej. `https://tu-tts-webapp.onrender.com`).

### ⚠️ Limitaciones del Plan Gratis de Render
1. **Inactividad (Spindown)**: Si nadie visita la página en 15 minutos, el servidor se "duerme" para ahorrar recursos. Cuando alguien vuelva a entrar, la primera carga tardará unos **50 a 60 segundos** en responder mientras la app "despierta".
2. **Límite mensual**: Cuentas con unas ~750 horas al mes, que cubren todo el mes si tienes 1 solo servicio corriendo, pero restan horas compartidas si tienes más apps.
3. **Filesystem Efímero**: Todas las carpetas se borran si el contenedor se reinicia o se duerme. Esto es **ideal para esta webapp**, ya que significa cero coste de mantenimiento en disco; los archivos de audio MP3 no se acumularán eternamente.

---

## 🛠 Instalación y Prueba Local

### 1. Requisitos Previos
- Python 3.11+

### 2. Preparar el Entorno
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 3. Ejecutar (Development)
```bash
python app.py
```
> Ingresa a [http://localhost:5000](http://localhost:5000) en la misma red.
> **Consejo para probar desde otro dispositivo móvil en tu casa:** Ejecuta el comando anterior, busca la IP local IPv4 de tu PC (ej. `192.168.1.50`) y entra a `http://192.168.1.50:5000` desde el navegador del móvil.
