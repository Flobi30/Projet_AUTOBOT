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
cp -f main.py main.py.bak
cp -f src/autobot/main_enhanced.py src/autobot/main_enhanced.py.bak
cp -f src/autobot/autobot_security/config.py src/autobot/autobot_security/config.py.bak
cp -f src/autobot/autobot_security/auth/__init__.py src/autobot/autobot_security/auth/__init__.py.bak
cp -f .env .env.bak

echo -e "${YELLOW}Mise à jour depuis GitHub...${NC}"
git fetch origin
git checkout main
git pull origin main

mkdir -p src/autobot/autobot_security/auth

echo -e "${YELLOW}Création du fichier ModifiedUserManager.py...${NC}"
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
import logging
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

if SECRET_KEY == "your-secret-key":
    logging.warning("Using default SECRET_KEY value. This is insecure for production!")

if ALGORITHM != "HS256":
    logging.info(f"Using non-default JWT algorithm: {ALGORITHM}")
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

echo -e "${YELLOW}Création ou mise à jour du fichier .env...${NC}"
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
PYTHONPATH=src

ALPHA_KEY=ta_cle_alpha
TWELVE_KEY=ta_cle_twelve
FRED_KEY=ta_cle_fred
NEWSAPI_KEY=ta_cle_news
SHOPIFY_KEY=ta_cle_shopify
SHOPIFY_SHOP_NAME=nom_de_ton_shop

LICENSE_KEY=<votre_clé_de_licence>

JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
TOKEN_EXPIRE_MINUTES=1440

ADMIN_USER=admin
ADMIN_PASSWORD=votre_mot_de_passe_fort

ENVIRONMENT=development
EOF
    echo -e "${YELLOW}IMPORTANT: Veuillez modifier les valeurs sensibles dans .env${NC}"
    echo -e "${YELLOW}Exécutez: sudo nano .env${NC}"
else
    if ! grep -q "JWT_SECRET_KEY" .env; then
        echo -e "\n# JWT Authentication" >> .env
        echo "JWT_SECRET_KEY=your-secret-key" >> .env
        echo "JWT_ALGORITHM=HS256" >> .env
        echo "TOKEN_EXPIRE_MINUTES=1440" >> .env
    fi
    
    if ! grep -q "ADMIN_USER" .env; then
        echo -e "\n# Admin Credentials" >> .env
        echo "ADMIN_USER=admin" >> .env
        echo "ADMIN_PASSWORD=votre_mot_de_passe_fort" >> .env
    fi
    
    if ! grep -q "ENVIRONMENT" .env; then
        echo -e "\n# Environment" >> .env
        echo "ENVIRONMENT=development" >> .env
    fi
    
    if ! grep -q "LICENSE_KEY" .env; then
        echo -e "\n# License" >> .env
        echo "LICENSE_KEY=<votre_clé_de_licence>" >> .env
    fi
    
    echo -e "${YELLOW}IMPORTANT: Veuillez vérifier et modifier les valeurs sensibles dans .env${NC}"
    echo -e "${YELLOW}Exécutez: sudo nano .env${NC}"
fi

echo -e "${YELLOW}Installation de python-dotenv...${NC}"
pip install python-dotenv

echo -e "${YELLOW}Définition des permissions...${NC}"
chmod 644 src/autobot/autobot_security/auth/modified_user_manager.py
chmod 644 src/autobot/autobot_security/auth/__init__.py
chmod 644 src/autobot/autobot_security/config.py
chmod 644 src/autobot/main_enhanced.py
chmod 644 main.py
chmod 644 .env

echo -e "${GREEN}=== Redémarrage du service AUTOBOT ===${NC}"
echo -e "${YELLOW}Pour redémarrer le service AUTOBOT, exécutez:${NC}"
echo -e "${GREEN}sudo supervisorctl restart autobot${NC}"
echo -e "\n${YELLOW}Pour vérifier les logs, exécutez:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot.log${NC}"

echo -e "\n${GREEN}=== Fin du script ===${NC}"
echo -e "${YELLOW}Si vous rencontrez des erreurs, vérifiez les logs d'erreur avec:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot_error.log${NC}"
