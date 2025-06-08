#!/bin/bash
set -e

# Variables
DATE=$(date +%Y%m%d_%H%M%S)
IMAGE_TAG="flobi30/autobot-fastapi:${DATE}"
STAGING_CONTAINER="autobot-fastapi-staging"
PROD_CONTAINER="autobot-simple"

echo "=== Building FastAPI staging image ==="
docker build -t ${IMAGE_TAG} .

echo "=== Starting staging container ==="
docker run -d \
  --name ${STAGING_CONTAINER} \
  -p 8001:8000 \
  -v /home/autobot/Projet_AUTOBOT/data:/app/data \
  -v /home/autobot/Projet_AUTOBOT/logs:/app/logs \
  -v /home/autobot/Projet_AUTOBOT/config:/app/config \
  ${IMAGE_TAG}

echo "=== Staging environment ready at http://144.76.16.177:8001 ==="
