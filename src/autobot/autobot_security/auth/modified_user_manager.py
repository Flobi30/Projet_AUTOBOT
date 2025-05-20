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
