# Dockerfile pour AUTOBOT V2
# Multi-architecture: supporte x86 (Intel/AMD) et ARM64 (CAX11)
FROM python:3.11-slim

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# INF-01: Créer utilisateur non-root
RUN useradd --system --no-create-home --shell /bin/false appuser

# Répertoire de travail
WORKDIR /app

# Copie des requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copie du code
COPY src/ /app/src/
COPY .env.example /app/.env

# Variables d'environnement par défaut
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

# INF-01: Fixer les permissions avant de basculer l'utilisateur
RUN chown -R appuser:appuser /app

# Port exposé pour l'API dashboard
EXPOSE 8080

# INF-01: Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# INF-01: Exécuter en tant qu'utilisateur non-root
USER appuser

# Commande de démarrage (async)
CMD ["python", "-u", "src/autobot/v2/main_async.py"]
