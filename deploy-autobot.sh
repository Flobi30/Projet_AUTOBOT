#!/bin/bash
set -e

# Configuration
PROD_SERVER="144.76.16.177"
SSH_KEY="/home/ubuntu/.ssh/id_ed25519_devin"
DATE=$(date +%Y%m%d_%H%M%S)
IMAGE_TAG="flobi30/autobot-fastapi:${DATE}"

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

ssh_exec() {
    ssh -i ${SSH_KEY} root@${PROD_SERVER} "$1"
}

# Main deployment function
deploy_staging() {
    log "=== Building FastAPI Docker image ==="
    docker build -t ${IMAGE_TAG} .
    docker tag ${IMAGE_TAG} flobi30/autobot-fastapi:latest
    
    log "=== Copying image to production server ==="
    docker save ${IMAGE_TAG} | ssh -i ${SSH_KEY} root@${PROD_SERVER} "docker load"
    
    log "=== Starting staging environment ==="
    ssh_exec "
        docker stop autobot-fastapi-staging 2>/dev/null || true
        docker rm autobot-fastapi-staging 2>/dev/null || true
        docker run -d \
          --name autobot-fastapi-staging \
          -p 8001:8000 \
          -v /home/autobot/Projet_AUTOBOT/data:/app/data \
          -v /home/autobot/Projet_AUTOBOT/logs:/app/logs \
          -v /home/autobot/Projet_AUTOBOT/config:/app/config \
          ${IMAGE_TAG}
    "
    
    log "=== Staging environment ready at http://144.76.16.177:8001 ==="
}

deploy_production() {
    log "=== Creating production backup ==="
    ssh_exec "
        mkdir -p /home/autobot/backup-${DATE}
        cp -r /etc/nginx/sites-available /home/autobot/backup-${DATE}/
        cp -r /etc/nginx/sites-enabled /home/autobot/backup-${DATE}/
        docker export autobot-simple > /home/autobot/backup-${DATE}/autobot-simple.tar 2>/dev/null || true
    "
    
    log "=== Deploying to production ==="
    ssh_exec "
        # Stop current container
        docker stop autobot-simple 2>/dev/null || true
        
        # Switch nginx configuration
        rm -f /etc/nginx/sites-enabled/autobot-static
        rm -f /etc/nginx/sites-enabled/autobot-standalone*
        ln -sf /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/
        systemctl reload nginx
        
        # Start FastAPI container
        docker stop autobot-fastapi-prod 2>/dev/null || true
        docker rm autobot-fastapi-prod 2>/dev/null || true
        docker run -d \
          --name autobot-fastapi-prod \
          -p 8000:8000 \
          -v /home/autobot/Projet_AUTOBOT/data:/app/data \
          -v /home/autobot/Projet_AUTOBOT/logs:/app/logs \
          -v /home/autobot/Projet_AUTOBOT/config:/app/config \
          --restart unless-stopped \
          ${IMAGE_TAG}
    "
    
    log "=== Production deployment completed ==="
}

rollback_production() {
    log "=== Rolling back to static deployment ==="
    ssh_exec "
        # Stop FastAPI container
        docker stop autobot-fastapi-prod 2>/dev/null || true
        docker rm autobot-fastapi-prod 2>/dev/null || true
        
        # Restore static nginx config
        rm -f /etc/nginx/sites-enabled/autobot
        ln -sf /etc/nginx/sites-available/autobot-static /etc/nginx/sites-enabled/
        systemctl reload nginx
        
        # Restart original container
        docker start autobot-simple 2>/dev/null || docker run -d \
          --name autobot-simple \
          -p 8000:8000 \
          python:3.10-slim bash -c 'pip install fastapi uvicorn jinja2 python-multipart requests && mkdir -p /app && sleep infinity'
    "
    
    log "=== Rollback completed ==="
}

# Main execution
case "${1:-help}" in
    "staging")
        deploy_staging
        ;;
    "production")
        deploy_production
        ;;
    "rollback")
        rollback_production
        ;;
    "help"|*)
        echo "Usage: $0 {staging|production|rollback}"
        echo "  staging    - Deploy to staging environment (port 8001)"
        echo "  production - Deploy to production (port 8000)"
        echo "  rollback   - Rollback to static deployment"
        exit 1
        ;;
esac
