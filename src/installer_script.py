"""
AUTOBOT Windows Installer Script

Ce script est le point d'entrée principal de l'installateur Windows pour AUTOBOT.
Il gère l'installation complète en un seul clic, y compris la vérification des prérequis,
l'installation des dépendances, et le démarrage automatique du serveur.
"""

import os
import sys
import subprocess
import platform
import webbrowser
import tkinter as tk
from tkinter import ttk
import threading
import time
import random
import string
import json
import shutil
from pathlib import Path

from installer_gui import InstallerGUI
from installer_utils import (
    check_python_installed,
    install_embedded_python,
    clone_repository,
    install_dependencies,
    generate_secure_key,
    create_config_files,
    create_shortcuts,
    start_autobot_server
)

def main():
    """Fonction principale de l'installateur."""
    root = tk.Tk()
    app = InstallerGUI(root)
    
    install_thread = threading.Thread(target=run_installation, args=(app,))
    install_thread.daemon = True
    install_thread.start()
    
    root.mainloop()

def run_installation(app):
    """
    Exécute le processus d'installation complet.
    
    Args:
        app: Instance de l'interface graphique
    """
    app.update_status("Vérification des prérequis système...")
    
    if not check_python_installed():
        app.update_status("Installation de Python...")
        install_embedded_python()
    
    app.update_status("Téléchargement d'AUTOBOT...")
    app.update_progress(20)
    clone_repository()
    
    app.update_status("Installation des dépendances...")
    app.update_progress(40)
    install_dependencies()
    
    app.update_status("Configuration d'AUTOBOT...")
    app.update_progress(60)
    jwt_secret = generate_secure_key(32)
    admin_password = generate_secure_key(12)
    create_config_files(jwt_secret, admin_password)
    
    app.update_status("Création des raccourcis...")
    app.update_progress(80)
    create_shortcuts()
    
    app.update_status("Démarrage d'AUTOBOT...")
    app.update_progress(100)
    server_url = start_autobot_server()
    
    app.installation_complete(server_url, admin_password)

if __name__ == "__main__":
    main()
