#!/usr/bin/env python3
"""
Point d'entrée principal pour AUTOBOT sans dépendance openhands
Maintient les fonctionnalités d'AutobotKernel tout en utilisant FastAPI
"""
import os
import sys
import uvicorn

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

class AutobotKernel:
    """
    Kernel principal d'AUTOBOT : orchestre les IA, la duplication, la
    collecte de données et le déploiement.
    """

    def __init__(self):
        print("🟢 AutobotKernel initialized")

    def run(self):
        print("🚀 AutobotKernel running…")
        
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
