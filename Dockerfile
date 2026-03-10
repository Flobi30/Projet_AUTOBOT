FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY src/ ./src/

# Création du répertoire de données et logs
RUN mkdir -p data logs

# Variables d'environnement par défaut
ENV PYTHONPATH=/app/src
ENV AUTOBOT_SANDBOX=true

# Point d'entrée
CMD ["python", "-m", "autobot.main"]
