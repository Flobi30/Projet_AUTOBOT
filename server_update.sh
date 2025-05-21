#!/bin/bash
# Script de mise à jour AUTOBOT depuis GitHub
# Amélioré avec gestion d'erreurs, journalisation et vérification de service

# Définition des couleurs pour les messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration des chemins
AUTOBOT_DIR="/home/autobot/Projet_AUTOBOT"
BACKUP_DIR="${AUTOBOT_DIR}/backups/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${AUTOBOT_DIR}/logs/update_$(date +%Y%m%d_%H%M%S).log"

# Création des répertoires nécessaires
mkdir -p "${BACKUP_DIR}" "${AUTOBOT_DIR}/logs"

# Fonction de journalisation
log() {
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${message}" | tee -a "$LOG_FILE"
}

# Fonction pour les messages de succès
log_success() {
    log "${GREEN}$1${NC}"
}

# Fonction pour les messages d'avertissement
log_warning() {
    log "${YELLOW}$1${NC}"
}

# Fonction pour les messages d'erreur
log_error() {
    log "${RED}$1${NC}"
}

# Gestion des erreurs
handle_error() {
    log_error "Une erreur s'est produite à la ligne $1"
    log_warning "Restauration des fichiers de configuration..."

    # Restaurer les fichiers de configuration
    if [ -d "${BACKUP_DIR}" ]; then
        cp -f "${BACKUP_DIR}"/* "${AUTOBOT_DIR}/" 2>/dev/null || true
        log_success "Restauration terminée."
    else
        log_error "Répertoire de sauvegarde introuvable."
    fi

    exit 1
}

# Configurer le gestionnaire d'erreurs
trap 'handle_error $LINENO' ERR

# Vérification du répertoire
log_success "=== Script de mise à jour AUTOBOT depuis GitHub ==="

if [ ! -d "$AUTOBOT_DIR" ]; then
    log_error "ERREUR: Le répertoire $AUTOBOT_DIR n'existe pas."
    log_warning "Ce script doit être exécuté sur le serveur Hetzner."
    exit 1
fi

cd "$AUTOBOT_DIR"
log "Répertoire de travail: $(pwd)"

# Sauvegarde des fichiers importants
log_warning "Sauvegarde des fichiers importants..."
if [ -f "main.py" ]; then cp -f main.py "${BACKUP_DIR}/main.py.bak"; fi
if [ -f "src/autobot/main_enhanced.py" ]; then cp -f src/autobot/main_enhanced.py "${BACKUP_DIR}/main_enhanced.py.bak"; fi
if [ -f "src/autobot/autobot_security/config.py" ]; then cp -f src/autobot/autobot_security/config.py "${BACKUP_DIR}/config.py.bak"; fi
if [ -f "src/autobot/autobot_security/auth/__init__.py" ]; then cp -f src/autobot/autobot_security/auth/__init__.py "${BACKUP_DIR}/__init__.py.bak"; fi
if [ -f ".env" ]; then cp -f .env "${BACKUP_DIR}/.env.bak"; fi
log_success "Sauvegarde terminée."

# Mise à jour depuis GitHub
log_warning "Mise à jour depuis GitHub..."
git fetch origin || { log_error "Échec de git fetch"; exit 1; }
git checkout main || { log_error "Échec de git checkout main"; exit 1; }
git pull origin main || { log_error "Échec de git pull"; exit 1; }
log_success "Code source mis à jour avec succès."

# Création des répertoires nécessaires
mkdir -p src/autobot/autobot_security/auth

# Mise à jour des fichiers
log_warning "Mise à jour des fichiers de configuration..."

# Création du fichier ModifiedUserManager.py
log "Création du fichier ModifiedUserManager.py..."
cat > src/autobot/autobot_security/auth/modified_user_manager.py << 'EOF'
"""
Version améliorée du UserManager qui initialise un utilisateur administrateur
par défaut à partir des variables d'environnement.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from autobot.autobot_security.auth.user_manager import UserManager

load_dotenv()

logger = logging.getLogger(__name__)

class ModifiedUserManager(UserManager):
    """
    Version modifiée de UserManager qui crée automatiquement un utilisateur
    administrateur par défaut à partir des variables d'environnement.
    """

    def __init__(self, users_file: str = None):
        """
        Initialise le UserManager modifié.

        Args:
            users_file: Chemin vers le fichier users.json
        """
        if users_file is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            users_file = os.path.join(base_dir, "config", "users.json")

        super().__init__(users_file)

        if not self.users.get("users"):
            self._create_default_admin_user()

    def _create_default_admin_user(self):
        """
        Crée un utilisateur administrateur par défaut à partir des variables d'environnement.
        """
        try:
            admin_user = os.getenv("ADMIN_USER", "admin")
            admin_password = os.getenv("ADMIN_PASSWORD", "votre_mot_de_passe_fort")

            logger.info(f"Création de l'utilisateur administrateur par défaut : {admin_user}")
            self.register_user(
                username=admin_user,
                password=admin_password,
                email="admin@autobot.local",
                role="admin"
            )
            logger.info("Utilisateur administrateur créé avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'utilisateur administrateur par défaut : {str(e)}")
EOF

# Mise à jour de __init__.py
log "Mise à jour de __init__.py..."
cat > src/autobot/autobot_security/auth/__init__.py << 'EOF'
from .jwt_handler import (
    create_access_token,
    decode_token,
    get_current_user,
    verify_license_key,
    generate_license_key
)
from .modified_user_manager import ModifiedUserManager

__all__ = [
    'create_access_token',
    'decode_token',
    'get_current_user',
    'verify_license_key',
    'generate_license_key',
    'ModifiedUserManager'
]
EOF

# Mise à jour de config.py
log "Mise à jour de config.py..."
cat > src/autobot/autobot_security/config.py << 'EOF'
import os
import logging
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

if SECRET_KEY == "your-secret-key":
    logging.warning("Using default SECRET_KEY value. This is insecure for production!")
    logging.warning("Please set JWT_SECRET_KEY in your .env file")

if ALGORITHM != "HS256":
    logging.info(f"Using non-default JWT algorithm: {ALGORITHM}")
EOF

# Mise à jour de main_enhanced.py
log "Mise à jour de main_enhanced.py..."
if [ -f "src/autobot/main_enhanced.py" ]; then
    sed -i '/from autobot.autobot_security.auth.user_manager import UserManager/a from autobot.autobot_security.auth.modified_user_manager import ModifiedUserManager' src/autobot/main_enhanced.py
    sed -i 's/user_manager = UserManager()/user_manager = ModifiedUserManager()/' src/autobot/main_enhanced.py
    log_success "main_enhanced.py mis à jour avec succès."
else
    log_warning "Fichier main_enhanced.py introuvable."
fi

# Mise à jour de main.py
log "Mise à jour de main.py..."
cat > main.py << 'EOF'
#!/usr/bin/env python3
"""
Point d'entrée principal pour AUTOBOT sans dépendance openhands
Maintient les fonctionnalités d'AutobotKernel tout en utilisant FastAPI
"""
import os
import sys
import uvicorn
import logging

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autobot.log")
    ]
)

logger = logging.getLogger(__name__)

class AutobotKernel:
    """
    Kernel principal d'AUTOBOT : orchestre les IA, la duplication, la
    collecte de données et le déploiement.
    """

    def __init__(self):
        logger.info("🟢 AutobotKernel initialized")

        try:
            from src.autobot.autobot_security.auth.modified_user_manager import ModifiedUserManager
            self.user_manager = ModifiedUserManager()
            logger.info("✅ Système d'authentification initialisé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation du système d'authentification : {str(e)}")

    def run(self):
        logger.info("🚀 AutobotKernel running…")

        from src.autobot.main import app
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

def main():
    """
    Fonction principale qui lance l'application AUTOBOT
    """
    bot = AutobotKernel()
    bot.run()

if __name__ == "__main__":
    main()
EOF

# Création ou mise à jour du fichier .env
log_warning "Création ou mise à jour du fichier .env..."
if [ ! -f ".env" ]; then
    JWT_KEY=$(openssl rand -hex 32)

    cat > .env << EOF
PYTHONPATH=src

JWT_SECRET_KEY=${JWT_KEY}
JWT_ALGORITHM=HS256
TOKEN_EXPIRE_MINUTES=1440

ALPHA_KEY=ta_cle_alpha
TWELVE_KEY=ta_cle_twelve
FRED_KEY=ta_cle_fred
NEWSAPI_KEY=ta_cle_news
SHOPIFY_KEY=ta_cle_shopify
SHOPIFY_SHOP_NAME=nom_de_ton_shop

LICENSE_KEY=<votre_clé_de_licence>


ADMIN_USER=admin
ADMIN_PASSWORD=votre_mot_de_passe_fort

ENVIRONMENT=development
EOF
    log_warning "IMPORTANT: Veuillez modifier les valeurs sensibles dans .env"
    log_warning "Exécutez: sudo nano .env"
else
    # Mise à jour du fichier .env existant
    if ! grep -q "JWT_SECRET_KEY" .env; then
        JWT_KEY=$(openssl rand -hex 32)

        echo -e "\n# JWT Authentication" >> .env
        echo "JWT_SECRET_KEY=${JWT_KEY}" >> .env
        echo "JWT_ALGORITHM=HS256" >> .env
        echo "TOKEN_EXPIRE_MINUTES=1440" >> .env

        echo -e "${YELLOW}Une nouvelle clé JWT forte a été générée et ajoutée à .env${NC}"
    fi

    if ! grep -q "LICENSE_KEY" .env; then
        echo -e "\n# License" >> .env
        echo "LICENSE_KEY=<votre_clé_de_licence>" >> .env
        echo -e "${YELLOW}IMPORTANT: Veuillez modifier la clé de licence dans .env${NC}"
        echo -e "${YELLOW}Exécutez: sudo nano .env${NC}"
    fi

    if ! grep -q "ADMIN_USER" .env; then
        echo -e "\n# Admin Credentials" >> .env
        echo "ADMIN_USER=admin" >> .env
        echo "ADMIN_PASSWORD=votre_mot_de_passe_fort" >> .env
        log "Variables d'administration ajoutées à .env"
    fi

    if ! grep -q "ENVIRONMENT" .env; then
        echo -e "\n# Environment" >> .env
        echo "ENVIRONMENT=development" >> .env
        log "Variable d'environnement ajoutée à .env"
    fi

    if ! grep -q "LICENSE_KEY" .env; then
        echo -e "\n# License" >> .env
        echo "LICENSE_KEY=<votre_clé_de_licence>" >> .env
        log "Variable de licence ajoutée à .env"
    fi

    log_warning "IMPORTANT: Veuillez vérifier et modifier les valeurs sensibles dans .env"
    log_warning "Exécutez: sudo nano .env"
fi

# Installation des dépendances
log_warning "Installation des dépendances Python..."
pip install python-dotenv || { log_error "Échec de l'installation de python-dotenv"; exit 1; }

# Vérification du fichier requirements.txt
if [ -f "requirements.txt" ]; then
    log "Installation des dépendances depuis requirements.txt..."
    pip install -r requirements.txt || { log_warning "Certaines dépendances n'ont pas pu être installées"; }
else
    log_warning "Fichier requirements.txt introuvable. Création d'un fichier minimal..."
    cat > requirements.txt << 'EOF'
fastapi>=0.68.0
uvicorn>=0.15.0
python-dotenv>=0.19.0
python-jose[cryptography]>=3.3.0
python-multipart>=0.0.5
pytest>=6.2.5
httpx>=0.19.0
EOF
    log "Installation des dépendances depuis le nouveau requirements.txt..."
    pip install -r requirements.txt || { log_warning "Certaines dépendances n'ont pas pu être installées"; }
fi

# Définition des permissions
log "Définition des permissions..."
chmod 644 src/autobot/autobot_security/auth/modified_user_manager.py
chmod 644 src/autobot/autobot_security/auth/__init__.py
chmod 644 src/autobot/autobot_security/config.py
chmod 644 src/autobot/main_enhanced.py
chmod 644 main.py
chmod 644 .env
log_success "Permissions définies avec succès."

# Exécution des tests si disponibles
if [ -d "tests" ]; then
    log_warning "Exécution des tests unitaires..."
    python -m pytest tests/ -v || { log_warning "Certains tests ont échoué. Vérifiez les logs pour plus de détails."; }
else
    log_warning "Répertoire de tests introuvable. Les tests n'ont pas été exécutés."
fi

# Redémarrage du service
log_success "=== Redémarrage du service AUTOBOT ==="

# Vérification de la configuration supervisor
SUPERVISOR_CONF="/etc/supervisor/conf.d/autobot.conf"
if [ -f "$SUPERVISOR_CONF" ]; then
    log "Vérification de la configuration supervisor..."
    if command -v supervisorctl &> /dev/null; then
        supervisorctl reread || { log_warning "Échec de supervisorctl reread"; }
        supervisorctl update || { log_warning "Échec de supervisorctl update"; }

        # Redémarrage du service
        log "Redémarrage du service AUTOBOT..."
        supervisorctl restart autobot || { log_error "Échec du redémarrage du service"; }

        # Vérification du statut
        sleep 5
        STATUS=$(supervisorctl status autobot)
        log "Statut du service: $STATUS"

        if [[ "$STATUS" == *"RUNNING"* ]]; then
            log_success "Service AUTOBOT redémarré avec succès."
        else
            log_warning "AVERTISSEMENT: Le service n'est pas en état RUNNING."
            log_warning "Vérifiez les logs pour plus de détails: sudo tail -f /var/log/autobot/autobot.log"
        fi
    else
        log_warning "supervisorctl n'est pas disponible. Redémarrage manuel requis."
        log_warning "Pour redémarrer le service AUTOBOT, exécutez:"
        log_warning "sudo supervisorctl restart autobot"
    fi
else
    log_warning "Configuration supervisor introuvable: $SUPERVISOR_CONF"
    log_warning "Pour redémarrer le service AUTOBOT, exécutez:"
    log_warning "sudo supervisorctl restart autobot"
fi

log_warning "Pour vérifier les logs, exécutez:"
log_warning "sudo tail -f /var/log/autobot/autobot.log"

log_success "=== Fin du script ==="
log_warning "Si vous rencontrez des erreurs, vérifiez les logs d'erreur avec:"
log_warning "sudo tail -f /var/log/autobot/autobot_error.log"

# Résumé des opérations
log_success "Résumé des opérations:"
log "- Code source mis à jour depuis GitHub"
log "- Fichiers de configuration mis à jour"
log "- Dépendances Python installées"
if [ -d "tests" ]; then
    log "- Tests unitaires exécutés"
fi
if command -v supervisorctl &> /dev/null && [ -f "$SUPERVISOR_CONF" ]; then
    log "- Service AUTOBOT redémarré"
fi
log_success "Mise à jour terminée avec succès."

exit 0
