FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Configure working directory
WORKDIR /app

# Install basic underlying tools (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first (caching layer)
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . /app/

# Expose the default Gunicorn Port
EXPOSE 5000

# Production CMD using Gunicorn
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
