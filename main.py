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
