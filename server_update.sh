#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Script de mise à jour AUTOBOT depuis GitHub ===${NC}"

if [ ! -d "/home/autobot/Projet_AUTOBOT" ]; then
  echo -e "${RED}ERREUR: Le répertoire /home/autobot/Projet_AUTOBOT n'existe pas.${NC}"
  echo -e "${YELLOW}Ce script doit être exécuté sur le serveur Hetzner.${NC}"
  exit 1
fi

cd /home/autobot/Projet_AUTOBOT

echo -e "${YELLOW}Sauvegarde des fichiers importants...${NC}"
cp -f config/auth_config.json config/auth_config.json.bak
cp -f main.py main.py.bak
cp -f src/autobot/main_enhanced.py src/autobot/main_enhanced.py.bak
cp -f src/autobot/autobot_security/config.py src/autobot/autobot_security/config.py.bak
cp -f src/autobot/autobot_security/auth/__init__.py src/autobot/autobot_security/auth/__init__.py.bak

echo -e "${YELLOW}Mise à jour depuis GitHub...${NC}"
git fetch origin
git checkout main
git pull origin main

mkdir -p src/autobot/autobot_security/auth

echo -e "${YELLOW}Création du fichier ModifiedUserManager.py...${NC}"
cat > src/autobot/autobot_security/auth/modified_user_manager.py << 'EOF'
"""
Version améliorée du UserManager qui initialise un utilisateur administrateur
par défaut à partir du fichier auth_config.json.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List

from autobot.autobot_security.auth.user_manager import UserManager

logger = logging.getLogger(__name__)

class ModifiedUserManager(UserManager):
    """
    Version modifiée de UserManager qui crée automatiquement un utilisateur
    administrateur par défaut à partir de auth_config.json.
    """
    
    def __init__(self, users_file: str = None, auth_config_file: str = None):
        """
        Initialise le UserManager modifié.
        
        Args:
            users_file: Chemin vers le fichier users.json
            auth_config_file: Chemin vers le fichier auth_config.json
        """
        if auth_config_file is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            auth_config_file = os.path.join(base_dir, "config", "auth_config.json")
            
        if users_file is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
            users_file = os.path.join(base_dir, "config", "users.json")
        
        super().__init__(users_file)
        
        if not self.users.get("users"):
            self._create_default_admin_user(auth_config_file)
    
    def _create_default_admin_user(self, auth_config_file: str):
        """
        Crée un utilisateur administrateur par défaut à partir de auth_config.json.
        
        Args:
            auth_config_file: Chemin vers le fichier auth_config.json
        """
        try:
            if os.path.exists(auth_config_file):
                with open(auth_config_file, 'r') as f:
                    auth_config = json.load(f)
                
                admin_user = auth_config.get("admin_user", "admin")
                admin_password = auth_config.get("admin_password", "votre_mot_de_passe_fort")
                
                logger.info(f"Création de l'utilisateur administrateur par défaut : {admin_user}")
                self.register_user(
                    username=admin_user,
                    password=admin_password,
                    email="admin@autobot.local",
                    role="admin"
                )
                logger.info("Utilisateur administrateur créé avec succès.")
            else:
                logger.error(f"Fichier de configuration d'authentification introuvable : {auth_config_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'utilisateur administrateur par défaut : {str(e)}")
EOF

echo -e "${YELLOW}Mise à jour de __init__.py...${NC}"
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

echo -e "${YELLOW}Mise à jour de config.py...${NC}"
cat > src/autobot/autobot_security/config.py << 'EOF'
import os
import json
import logging

AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config', 'auth_config.json')

SECRET_KEY = 'your-secret-key'
ALGORITHM = 'HS256'

try:
    if os.path.exists(AUTH_CONFIG_PATH):
        with open(AUTH_CONFIG_PATH, 'r') as f:
            auth_config = json.load(f)
            SECRET_KEY = auth_config.get('jwt_secret', SECRET_KEY)
            ALGORITHM = auth_config.get('jwt_algorithm', ALGORITHM)
except Exception as e:
    logging.error(f"Error loading auth_config.json: {str(e)}")
    logging.warning("Using default SECRET_KEY and ALGORITHM values")
EOF

echo -e "${YELLOW}Mise à jour de main_enhanced.py...${NC}"
sed -i '/from autobot.autobot_security.auth.user_manager import UserManager/a from autobot.autobot_security.auth.modified_user_manager import ModifiedUserManager' src/autobot/main_enhanced.py
sed -i 's/user_manager = UserManager()/user_manager = ModifiedUserManager()/' src/autobot/main_enhanced.py

echo -e "${YELLOW}Mise à jour de main.py...${NC}"
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

echo -e "${YELLOW}Vérification de auth_config.json...${NC}"
if [ ! -f "config/auth_config.json" ]; then
  echo -e "${YELLOW}Le fichier auth_config.json n'existe pas, nous allons le créer${NC}"
  mkdir -p config
  cat > config/auth_config.json << 'EOF'
{
  "admin_user": "admin",
  "admin_password": "votre_mot_de_passe_fort",
  "jwt_secret": "your-secret-key",
  "jwt_algorithm": "HS256",
  "token_expire_minutes": 1440
}
EOF
  echo -e "${YELLOW}IMPORTANT: Veuillez modifier le mot de passe dans auth_config.json${NC}"
  echo -e "${YELLOW}Exécutez: sudo nano config/auth_config.json${NC}"
else
  echo -e "${GREEN}✓ Le fichier auth_config.json existe déjà${NC}"
fi

echo -e "${YELLOW}Création ou mise à jour du fichier .env...${NC}"
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
PYTHONPATH=src
LICENSE_KEY=AUTOBOT-12345678-ABCDEFGH-IJKLMNOP-QRSTUVWX
EOF
    echo -e "${YELLOW}IMPORTANT: Veuillez modifier la clé de licence dans .env${NC}"
    echo -e "${YELLOW}Exécutez: sudo nano .env${NC}"
else
    if ! grep -q "LICENSE_KEY" .env; then
        echo "LICENSE_KEY=AUTOBOT-12345678-ABCDEFGH-IJKLMNOP-QRSTUVWX" >> .env
        echo -e "${YELLOW}IMPORTANT: Veuillez modifier la clé de licence dans .env${NC}"
        echo -e "${YELLOW}Exécutez: sudo nano .env${NC}"
    fi
fi

echo -e "${YELLOW}Installation de python-dotenv...${NC}"
pip install python-dotenv

echo -e "${YELLOW}Définition des permissions...${NC}"
chmod 644 src/autobot/autobot_security/auth/modified_user_manager.py
chmod 644 src/autobot/autobot_security/auth/__init__.py
chmod 644 src/autobot/autobot_security/config.py
chmod 644 src/autobot/main_enhanced.py
chmod 644 main.py
chmod 644 config/auth_config.json
chmod 644 .env

echo -e "${GREEN}=== Redémarrage du service AUTOBOT ===${NC}"
echo -e "${YELLOW}Pour redémarrer le service AUTOBOT, exécutez:${NC}"
echo -e "${GREEN}sudo supervisorctl restart autobot${NC}"
echo -e "\n${YELLOW}Pour vérifier les logs, exécutez:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot.log${NC}"

echo -e "\n${GREEN}=== Fin du script ===${NC}"
echo -e "${YELLOW}Si vous rencontrez des erreurs, vérifiez les logs d'erreur avec:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot_error.log${NC}"
