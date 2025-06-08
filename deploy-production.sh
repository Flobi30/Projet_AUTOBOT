#!/bin/bash
set -e

ACTION=${1:-deploy}
BACKUP_DIR="/home/autobot/backup-$(date +%Y%m%d)"

case $ACTION in
  "backup")
    echo "=== Creating backup ==="
    mkdir -p ${BACKUP_DIR}
    cp -r /etc/nginx/sites-available ${BACKUP_DIR}/
    cp -r /etc/nginx/sites-enabled ${BACKUP_DIR}/
    docker export autobot-simple > ${BACKUP_DIR}/autobot-simple.tar
    echo "Backup created in ${BACKUP_DIR}"
    ;;
    
  "deploy")
    echo "=== Deploying FastAPI to production ==="
    # Stop current container
    docker stop autobot-simple || true
    
    # Disable static nginx config
    rm -f /etc/nginx/sites-enabled/autobot-static
    rm -f /etc/nginx/sites-enabled/autobot-standalone*
    
    # Enable FastAPI proxy config
    ln -sf /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/
    systemctl reload nginx
    
    # Start new FastAPI container
    docker run -d \
      --name autobot-fastapi-prod \
      -p 8000:8000 \
      -v /home/autobot/Projet_AUTOBOT/data:/app/data \
      -v /home/autobot/Projet_AUTOBOT/logs:/app/logs \
      -v /home/autobot/Projet_AUTOBOT/config:/app/config \
      --restart unless-stopped \
      flobi30/autobot-fastapi:latest
    
    echo "=== FastAPI deployed to production ==="
    ;;
    
  "rollback")
    echo "=== Rolling back to static deployment ==="
    # Stop FastAPI container
    docker stop autobot-fastapi-prod || true
    docker rm autobot-fastapi-prod || true
    
    # Restore static nginx config
    rm -f /etc/nginx/sites-enabled/autobot
    ln -sf /etc/nginx/sites-available/autobot-static /etc/nginx/sites-enabled/
    systemctl reload nginx
    
    # Restart original container
    docker start autobot-simple || docker run -d \
      --name autobot-simple \
      -p 8000:8000 \
      python:3.10-slim bash -c 'pip install fastapi uvicorn && sleep infinity'
    
    echo "=== Rollback completed ==="
    ;;
    
  *)
    echo "Usage: $0 {backup|deploy|rollback}"
    exit 1
    ;;
esac
