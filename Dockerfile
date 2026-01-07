FROM python:3.10-slim

WORKDIR /app

# 1) Installer les dépendances système pour compiler les wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
       build-essential \
       python3-dev \
       libffi-dev \
       libssl-dev \
       libevdev-dev \
       cargo \
       rustc \
    && rm -rf /var/lib/apt/lists/*

# 2) Copier les manifestes de dépendances
COPY setup.py requirements.txt requirements.dev.txt ./

# 3) Copier le code source pour que pip install -e . voie src/
COPY src/ ./src/

# 4) Mettre pip à jour et installer le package en mode editable
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e . && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements.dev.txt

# 5) Copier le reste (scripts, k8s, etc.)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "autobot.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
