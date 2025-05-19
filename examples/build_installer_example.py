"""
Script de construction de l'installateur Windows pour AUTOBOT

Ce script automatise la création de l'exécutable Windows (.exe) pour AUTOBOT
en utilisant PyInstaller.
"""

import os
import sys
import subprocess
import shutil
import urllib.request
import zipfile
import tempfile

RESOURCES_DIR = "resources"
OUTPUT_DIR = "dist"
PYTHON_VERSION = "3.10.0"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
AUTOBOT_LOGO_URL = "https://raw.githubusercontent.com/Flobi30/Projet_AUTOBOT/main/src/autobot/ui/static/img/logo.png"

def create_resources():
    """Crée les ressources nécessaires pour l'installateur."""
    print("Création des ressources...")
    
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    
    python_embed_dir = os.path.join(RESOURCES_DIR, "python_embed")
    os.makedirs(python_embed_dir, exist_ok=True)
    
    python_zip = os.path.join(tempfile.gettempdir(), "python_embed.zip")
    print(f"Téléchargement de Python {PYTHON_VERSION}...")
    urllib.request.urlretrieve(PYTHON_EMBED_URL, python_zip)
    
    with zipfile.ZipFile(python_zip, 'r') as zip_ref:
        zip_ref.extractall(python_embed_dir)
    
    logo_path = os.path.join(RESOURCES_DIR, "autobot_logo.png")
    print("Téléchargement du logo AUTOBOT...")
    urllib.request.urlretrieve(AUTOBOT_LOGO_URL, logo_path)
    
    banner_path = os.path.join(RESOURCES_DIR, "autobot_banner.png")
    if not os.path.exists(banner_path):
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', (500, 100), color=(18, 18, 18))
            d = ImageDraw.Draw(img)
            
            try:
                font = ImageFont.truetype("arial.ttf", 48)
            except:
                font = ImageFont.load_default()
            
            d.text((150, 30), "AUTOBOT", fill=(0, 255, 157), font=font)
            img.save(banner_path)
            print("Bannière créée avec succès")
        except:
            print("Impossible de créer la bannière, PIL non disponible")
            with open(banner_path.replace(".png", ".txt"), 'w') as f:
                f.write("AUTOBOT")
    
    ico_path = os.path.join(RESOURCES_DIR, "autobot_logo.ico")
    if not os.path.exists(ico_path):
        try:
            from PIL import Image
            
            img = Image.open(logo_path)
            img.save(ico_path)
            print("Icône créée avec succès")
        except:
            print("Impossible de créer l'icône, PIL non disponible")
    
    return True

def create_autobot_package():
    """Crée un package AUTOBOT préemballé."""
    print("Création du package AUTOBOT...")
    
    autobot_source_dir = os.path.join(RESOURCES_DIR, "autobot_source")
    os.makedirs(autobot_source_dir, exist_ok=True)
    
    essential_files = [
        "installer_script.py",
        "installer_gui.py",
        "installer_utils.py"
    ]
    
    for file in essential_files:
        src = os.path.join("src", file)
        dst = os.path.join(autobot_source_dir, file)
        if os.path.exists(src):
            shutil.copy(src, dst)
    
    return True

def package_installer():
    """Crée l'exécutable avec PyInstaller."""
    print("Création de l'exécutable...")
    
    try:
        import PyInstaller
    except ImportError:
        print("Installation de PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    icon_path = os.path.join(RESOURCES_DIR, "autobot_logo.ico")
    icon_param = f"--icon={icon_path}" if os.path.exists(icon_path) else ""
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "src/installer_script.py",
        "--name=AUTOBOT_Installer",
        "--onefile",
        "--windowed",
        icon_param,
        f"--add-data={RESOURCES_DIR};{RESOURCES_DIR}",
        "--hidden-import=tkinter",
        "--hidden-import=urllib.request",
        "--hidden-import=zipfile",
        "--hidden-import=threading",
        "--hidden-import=json",
        "--hidden-import=webbrowser"
    ]
    
    cmd = [param for param in cmd if param]
    
    result = subprocess.run(cmd)
    
    return result.returncode == 0

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
    
    installer_path = os.path.abspath(os.path.join(OUTPUT_DIR, "AUTOBOT_Installer.exe"))
    if os.path.exists(installer_path):
        print(f"\n✅ Installateur créé avec succès: {installer_path}")
    else:
        print("\n❌ L'installateur n'a pas été créé correctement")

if __name__ == "__main__":
    main()
