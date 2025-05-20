#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Script de mise à jour des fichiers d'authentification AUTOBOT ===${NC}"
echo -e "${YELLOW}Ce script va vous guider pour mettre à jour manuellement les fichiers nécessaires${NC}"
echo -e "${YELLOW}pour résoudre les problèmes d'authentification sur votre serveur Hetzner.${NC}"
echo ""

if [ ! -d "/home/autobot/Projet_AUTOBOT" ]; then
  echo -e "${RED}ERREUR: Le répertoire /home/autobot/Projet_AUTOBOT n'existe pas.${NC}"
  echo -e "${YELLOW}Ce script doit être exécuté sur le serveur Hetzner.${NC}"
  exit 1
fi

create_dir_if_not_exists() {
  if [ ! -d "$1" ]; then
    echo -e "${YELLOW}Création du répertoire $1${NC}"
    mkdir -p "$1"
  fi
}

create_file() {
  local file_path="$1"
  local dir_path=$(dirname "$file_path")
  
  create_dir_if_not_exists "$dir_path"
  
  echo -e "${GREEN}Création/Mise à jour du fichier $file_path${NC}"
  cat > "$file_path"
  
  echo -e "${GREEN}✓ Fichier $file_path créé avec succès${NC}"
}

echo -e "\n${GREEN}=== 1. Création du fichier ModifiedUserManager ===${NC}"
create_file "/home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/auth/modified_user_manager.py" << 'EOF'
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

echo -e "\n${GREEN}=== 2. Mise à jour du fichier __init__.py ===${NC}"
create_file "/home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/auth/__init__.py" << 'EOF'
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

echo -e "\n${GREEN}=== 3. Mise à jour du fichier config.py ===${NC}"
create_file "/home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/config.py" << 'EOF'
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

echo -e "\n${GREEN}=== 4. Mise à jour du fichier main_enhanced.py ===${NC}"
echo -e "${YELLOW}Nous allons modifier main_enhanced.py pour utiliser ModifiedUserManager${NC}"

if [ ! -f "/home/autobot/Projet_AUTOBOT/src/autobot/main_enhanced.py" ]; then
  echo -e "${RED}ERREUR: Le fichier main_enhanced.py n'existe pas.${NC}"
else
  sed -i '/from autobot.autobot_security.auth.user_manager import UserManager/a from autobot.autobot_security.auth.modified_user_manager import ModifiedUserManager' "/home/autobot/Projet_AUTOBOT/src/autobot/main_enhanced.py"
  
  sed -i 's/user_manager = UserManager()/user_manager = ModifiedUserManager()/' "/home/autobot/Projet_AUTOBOT/src/autobot/main_enhanced.py"
  
  echo -e "${GREEN}✓ Fichier main_enhanced.py mis à jour avec succès${NC}"
fi

echo -e "\n${GREEN}=== 5. Mise à jour du fichier main.py ===${NC}"
create_file "/home/autobot/Projet_AUTOBOT/main.py" << 'EOF'
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

echo -e "\n${GREEN}=== 6. Vérification de auth_config.json ===${NC}"
if [ ! -f "/home/autobot/Projet_AUTOBOT/config/auth_config.json" ]; then
  echo -e "${YELLOW}Le fichier auth_config.json n'existe pas, nous allons le créer${NC}"
  create_file "/home/autobot/Projet_AUTOBOT/config/auth_config.json" << 'EOF'
{
  "admin_user": "admin",
  "admin_password": "votre_mot_de_passe_fort",
  "jwt_secret": "your-secret-key",
  "jwt_algorithm": "HS256",
  "token_expire_minutes": 1440
}
EOF
  echo -e "${YELLOW}IMPORTANT: Veuillez modifier le mot de passe dans auth_config.json${NC}"
  echo -e "${YELLOW}Exécutez: sudo nano /home/autobot/Projet_AUTOBOT/config/auth_config.json${NC}"
else
  echo -e "${GREEN}✓ Le fichier auth_config.json existe déjà${NC}"
  echo -e "${YELLOW}Assurez-vous qu'il contient les paramètres nécessaires:${NC}"
  echo -e "${YELLOW}  - admin_user${NC}"
  echo -e "${YELLOW}  - admin_password${NC}"
  echo -e "${YELLOW}  - jwt_secret${NC}"
  echo -e "${YELLOW}  - jwt_algorithm${NC}"
  echo -e "${YELLOW}  - token_expire_minutes${NC}"
fi

echo -e "\n${GREEN}=== 7. Redémarrage du service AUTOBOT ===${NC}"
echo -e "${YELLOW}Pour redémarrer le service AUTOBOT, exécutez:${NC}"
echo -e "${GREEN}sudo supervisorctl restart autobot${NC}"
echo -e "\n${YELLOW}Pour vérifier les logs, exécutez:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot.log${NC}"
echo -e "\n${YELLOW}Recherchez dans les logs des messages comme:${NC}"
echo -e "${GREEN}- \"✅ Système d'authentification initialisé avec succès\"${NC}"
echo -e "${GREEN}- \"Création de l'utilisateur administrateur par défaut : admin\"${NC}"
echo -e "${GREEN}- \"Utilisateur administrateur créé avec succès.\"${NC}"

echo -e "\n${GREEN}=== 8. Test de l'accès à l'interface utilisateur ===${NC}"
echo -e "${YELLOW}Visitez l'URL de votre application (http://144.76.16.177 ou l'IP correspondante)${NC}"
echo -e "${YELLOW}et connectez-vous avec les identifiants définis dans auth_config.json:${NC}"
echo -e "${GREEN}- Nom d'utilisateur: admin${NC}"
echo -e "${GREEN}- Mot de passe: celui que vous avez défini dans auth_config.json${NC}"

echo -e "\n${GREEN}=== Fin du script ===${NC}"
echo -e "${YELLOW}Si vous rencontrez des erreurs, vérifiez les logs d'erreur avec:${NC}"
echo -e "${GREEN}sudo tail -f /var/log/autobot/autobot_error.log${NC}"
