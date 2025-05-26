#!/bin/bash

SERVER_URL="http://localhost:8000"
USERNAME="admin"
PASSWORD="votre_mot_de_passe_fort"
LICENSE_KEY="<votre_clé_de_licence>"
COOKIE_FILE="/tmp/autobot_cookies.txt"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Récupération du token CSRF..."
curl -s -c "$COOKIE_FILE" "$SERVER_URL/login" > /tmp/login_page.html

CSRF_TOKEN=$(grep -oP 'name="csrf_token" value="\K[^"]+' /tmp/login_page.html)

if [ -z "$CSRF_TOKEN" ]; then
    log "Erreur: Impossible de récupérer le token CSRF"
    exit 1
fi

log "Token CSRF récupéré: $CSRF_TOKEN"

log "Soumission du formulaire de connexion..."
RESPONSE=$(curl -s -i -b "$COOKIE_FILE" -c "$COOKIE_FILE" \
    -d "username=$USERNAME" \
    -d "password=$PASSWORD" \
    -d "license_key=$LICENSE_KEY" \
    -d "csrf_token=$CSRF_TOKEN" \
    -d "redirect_url=/dashboard/" \
    "$SERVER_URL/login")

if echo "$RESPONSE" | grep -q "302\|303"; then
    log "Authentification réussie! Redirection vers le dashboard."
    
    DASHBOARD=$(curl -s -b "$COOKIE_FILE" "$SERVER_URL/dashboard/")
    
    if [ $? -eq 0 ]; then
        log "Accès au dashboard réussi."
        echo "Vous êtes maintenant connecté à AUTOBOT."
    else
        log "Erreur lors de l'accès au dashboard."
        exit 1
    fi
else
    log "Erreur d'authentification. Réponse du serveur:"
    echo "$RESPONSE"
    exit 1
fi
