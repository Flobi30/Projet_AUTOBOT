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
