# Usa l'immagine base di Python
FROM python:3.12-slim

# Installa git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Imposta la directory di lavoro
WORKDIR /app

# Clona il repository GitHub
RUN git clone https://github.com/nzo66/tvproxy .

# Installa le dipendenze
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Espone la porta 7860 per Flask/Gunicorn
EXPOSE 7860

# Comando per avviare il server Flask con Gunicorn e 4 worker
CMD ["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:7860"]
