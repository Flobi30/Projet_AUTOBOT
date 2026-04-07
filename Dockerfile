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

# Permissions
RUN chown -R appuser:appuser /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fk https://localhost:8080/health || exit 1

USER appuser

CMD ["python", "-u", "src/autobot/v2/main_async.py"]
