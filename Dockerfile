# Usa l'immagine base Python ufficiale
FROM python:3.12-slim

# Installa dipendenze di sistema necessarie per gevent e build
RUN apt-get update && apt-get install -y \
    build-essential \
    libevent-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file dell'applicazione e requirements
COPY requirements.txt .
COPY app.py .

# Installa le dipendenze Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Espone la porta usata dall'app
EXPOSE 7860

# Comando ottimizzato per locale: worker asincroni e log in console
CMD ["gunicorn", "app:app", \
     "-w", "8", \
     "-b", "0.0.0.0:7860", \
     "--timeout", "300", \
     "--keep-alive", "30", \
     "--max-requests", "2000", \
     "--max-requests-jitter", "200", \
     "--worker-class", "gevent", \
     "--worker-connections", "200", \
     "--preload", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
