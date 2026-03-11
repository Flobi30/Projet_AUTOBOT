# Dockerfile pour AUTOBOT V2
FROM python:3.11-slim

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Copie des requirements
COPY src/autobot/v2/api/requirements.txt /app/requirements-api.txt
RUN pip install --no-cache-dir -r /app/requirements-api.txt

# Copie du code
COPY src/ /app/src/
COPY .env.example /app/.env

# Variables d'environnement par défaut
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Port exposé pour l'API dashboard
EXPOSE 8080

# Commande de démarrage
CMD ["python", "-u", "src/autobot/v2/main.py"]
