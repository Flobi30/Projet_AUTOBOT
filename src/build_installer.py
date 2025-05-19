"""
Script de construction de l'installateur Windows pour AUTOBOT

Ce script automatise la création de l'installateur Windows (.exe) pour AUTOBOT.
Il prépare les ressources, crée le package AUTOBOT, et génère l'exécutable final.
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

from installer_utils import create_resources, create_autobot_package, package_installer

def main():
    """Fonction principale pour la construction de l'installateur."""
    print("=== Construction de l'installateur Windows AUTOBOT ===")
    
    print("\n[1/3] Création des ressources...")
    if create_resources():
        print("✓ Ressources créées avec succès")
    else:
        print("✗ Erreur lors de la création des ressources")
        return
    
    print("\n[2/3] Création du package AUTOBOT...")
    if create_autobot_package():
        print("✓ Package AUTOBOT créé avec succès")
    else:
        print("✗ Erreur lors de la création du package AUTOBOT")
        return
    
    print("\n[3/3] Création de l'installateur...")
    if package_installer():
        print("✓ Installateur créé avec succès")
    else:
        print("✗ Erreur lors de la création de l'installateur")
        return
    
    installer_path = os.path.abspath("dist/AUTOBOT_Installer.exe")
    if os.path.exists(installer_path):
        print(f"\n✅ Installateur créé avec succès: {installer_path}")
    else:
        print("\n❌ L'installateur n'a pas été créé correctement")

if __name__ == "__main__":
    main()
