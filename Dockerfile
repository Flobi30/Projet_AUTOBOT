# Dockerfile multi-stage pour AUTOBOT V2 (Backend + Frontend)

# ==================== STAGE 1: Build Frontend ====================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/dashboard

# Copie des fichiers du frontend
COPY dashboard/package*.json ./
RUN npm install

COPY dashboard/ ./
RUN npm run build

# ==================== STAGE 2: Backend Python ====================
FROM python:3.11-slim

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Créer utilisateur non-root
RUN useradd --system --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copie des requirements et installation
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copie du code backend
COPY src/ /app/src/
COPY .env.example /app/.env

# Copie du frontend buildé depuis le stage 1
COPY --from=frontend-builder /app/dashboard/dist /app/dashboard/dist

# Variables d'environnement
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV DASHBOARD_STATIC_DIR=/app/dashboard/dist
ENV HEALTHCHECK_MODE=tls
ENV HEALTHCHECK_URL_TLS=https://localhost:8080/health
ENV HEALTHCHECK_URL_LOCAL=http://127.0.0.1:8080/health
ENV HEALTHCHECK_CA_CERT=/app/certs/server.crt

# Permissions
RUN chown -R appuser:appuser /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["/bin/sh", "-c", "if [ \"$HEALTHCHECK_MODE\" = \"local\" ]; then curl --fail --silent --show-error \"$HEALTHCHECK_URL_LOCAL\"; else curl --fail --silent --show-error --cacert \"$HEALTHCHECK_CA_CERT\" \"$HEALTHCHECK_URL_TLS\"; fi"]

USER appuser

CMD ["python", "-u", "src/autobot/v2/main_async.py"]
