"""
AUTOBOT Windows Installer Utilities

Ce module fournit des fonctions utilitaires pour l'installateur Windows d'AUTOBOT.
Il gère les vérifications système, l'installation des dépendances, et la configuration.
"""

import os
import sys
import subprocess
import platform
import zipfile
import shutil
import json
import random
import string
import time
import urllib.request
import tempfile
from pathlib import Path

def check_python_installed():
    """
    Vérifie si Python 3.9+ est installé.
    
    Returns:
        bool: True si Python 3.9+ est installé, False sinon
    """
    try:
        version = subprocess.run(
            ["python", "--version"], 
            capture_output=True, 
            text=True
        ).stdout
        
        import re
        match = re.search(r"Python (\d+)\.(\d+)\.(\d+)", version)
        if match:
            major, minor, _ = map(int, match.groups())
            return major >= 3 and minor >= 9
        
        return False
    except:
        return False

def install_embedded_python():
    """
    Télécharge et installe le Python Embeddable Package.
    
    Returns:
        bool: True si l'installation a réussi, False sinon
    """
    try:
        os.makedirs("resources", exist_ok=True)
        
        python_url = "https://www.python.org/ftp/python/3.10.0/python-3.10.0-embed-amd64.zip"
        
        python_zip = "resources/python_embedded.zip"
        if not os.path.exists(python_zip):
            urllib.request.urlretrieve(python_url, python_zip)
        
        with zipfile.ZipFile(python_zip, "r") as zip_ref:
            zip_ref.extractall("python_embedded")
        
        pip_url = "https://bootstrap.pypa.io/get-pip.py"
        pip_script = "resources/get-pip.py"
        if not os.path.exists(pip_script):
            urllib.request.urlretrieve(pip_url, pip_script)
        
        os.environ["PATH"] = os.path.abspath("python_embedded") + os.pathsep + os.environ["PATH"]
        
        subprocess.run(
            ["python_embedded/python.exe", "resources/get-pip.py"],
            check=True
        )
        
        return True
    except Exception as e:
        print(f"Erreur lors de l'installation de Python: {str(e)}")
        return False

def clone_repository():
    """
    Clone le dépôt AUTOBOT ou déploie la version préemballée.
    
    Returns:
        bool: True si le clonage a réussi, False sinon
    """
    try:
        if os.path.exists("resources/autobot_package.zip"):
            with zipfile.ZipFile("resources/autobot_package.zip", "r") as zip_ref:
                zip_ref.extractall("autobot")
        else:
            subprocess.run(
                ["git", "clone", "https://github.com/Flobi30/Projet_AUTOBOT.git", "autobot"],
                check=True
            )
        
        return True
    except Exception as e:
        print(f"Erreur lors du clonage du dépôt: {str(e)}")
        return False

def install_dependencies():
    """
    Installe toutes les dépendances requises.
    
    Returns:
        bool: True si l'installation a réussi, False sinon
    """
    try:
        subprocess.run(
            ["python", "-m", "pip", "install", "--upgrade", "pip"],
            check=True
        )
        
        subprocess.run(
            ["python", "-m", "pip", "install", "-r", "autobot/requirements.txt"],
            check=True
        )
        
        return True
    except Exception as e:
        print(f"Erreur lors de l'installation des dépendances: {str(e)}")
        return False

def generate_secure_key(length):
    """
    Génère une clé sécurisée aléatoire.
    
    Args:
        length: Longueur de la clé à générer
        
    Returns:
        str: Clé générée
    """
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

def create_config_files(jwt_secret, admin_password):
    """
    Crée les fichiers de configuration nécessaires.
    
    Args:
        jwt_secret: Clé secrète pour JWT
        admin_password: Mot de passe administrateur
        
    Returns:
        bool: True si la création a réussi, False sinon
    """
    try:
        os.makedirs("autobot/config", exist_ok=True)
        
        with open("autobot/.env", "w") as f:
            f.write(f"AUTOBOT_JWT_SECRET={jwt_secret}\n")
            f.write(f"AUTOBOT_ADMIN_PASSWORD={admin_password}\n")
            f.write("AUTOBOT_MAX_INSTANCES=100\n")
            f.write("AUTOBOT_DEPLOYMENT_TYPE=local\n")
        
        return True
    except Exception as e:
        print(f"Erreur lors de la création des fichiers de configuration: {str(e)}")
        return False

def create_shortcuts():
    """
    Crée les raccourcis sur le bureau et dans le menu Démarrer.
    
    Returns:
        bool: True si la création a réussi, False sinon
    """
    try:
        start_script = os.path.abspath("autobot/start_autobot.bat")
        
        with open(start_script, "w") as f:
            f.write("@echo off\n")
            f.write("cd %~dp0\n")
            f.write("python -m src.autobot.main\n")
        
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "AUTOBOT.lnk")
        
        ps_command = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{start_script}"
        $Shortcut.IconLocation = "{os.path.abspath('resources/autobot_logo.ico')}"
        $Shortcut.Save()
        """
        
        subprocess.run(["powershell", "-Command", ps_command], check=True)
        
        return True
    except Exception as e:
        print(f"Erreur lors de la création des raccourcis: {str(e)}")
        return False

def start_autobot_server():
    """
    Démarre le serveur AUTOBOT et retourne l'URL.
    
    Returns:
        str: URL du serveur AUTOBOT
    """
    try:
        subprocess.Popen(
            ["python", "-m", "src.autobot.main"],
            cwd="autobot",
            creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
        )
        
        time.sleep(5)
        
        return "http://localhost:8000"
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur: {str(e)}")
        return "http://localhost:8000"  # Retourner l'URL par défaut même en cas d'erreur

def package_installer():
    """
    Crée un package d'installation avec PyInstaller.
    
    Returns:
        bool: True si le packaging a réussi, False sinon
    """
    try:
        try:
            import PyInstaller
        except ImportError:
            subprocess.run(
                ["pip", "install", "pyinstaller"],
                check=True
            )
        
        spec_content = """

block_cipher = None

a = Analysis(
    ['installer_script.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources/*', 'resources'),
        ('autobot_package.zip', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AUTOBOT_Installer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/autobot_logo.ico',
)
        """
        
        with open("installer.spec", "w") as f:
            f.write(spec_content)
        
        subprocess.run(
            ["pyinstaller", "installer.spec", "--clean"],
            check=True
        )
        
        return True
    except Exception as e:
        print(f"Erreur lors du packaging de l'installateur: {str(e)}")
        return False

def create_resources():
    """
    Crée les ressources nécessaires pour l'installateur.
    
    Returns:
        bool: True si la création a réussi, False sinon
    """
    try:
        os.makedirs("resources", exist_ok=True)
        
        if not os.path.exists("resources/autobot_banner.png"):
            try:
                from PIL import Image, ImageDraw, ImageFont
                
                img = Image.new('RGB', (500, 100), color=(53, 59, 72))
                d = ImageDraw.Draw(img)
                
                try:
                    font = ImageFont.truetype("arial.ttf", 40)
                except:
                    font = ImageFont.load_default()
                
                d.text((150, 30), "AUTOBOT", fill=(255, 255, 255), font=font)
                
                img.save("resources/autobot_banner.png")
            except:
                with open("resources/create_banner.txt", "w") as f:
                    f.write("Pour créer une bannière, utilisez un logiciel d'édition d'image et créez une image de 500x100 pixels.")
        
        if not os.path.exists("resources/autobot_logo.ico"):
            try:
                from PIL import Image, ImageDraw
                
                img = Image.new('RGB', (256, 256), color=(53, 59, 72))
                d = ImageDraw.Draw(img)
                
                d.ellipse((50, 50, 206, 206), fill=(0, 168, 255))
                
                img.save("resources/autobot_logo.png")
                
                img.save("resources/autobot_logo.ico")
            except:
                with open("resources/create_icon.txt", "w") as f:
                    f.write("Pour créer une icône, utilisez un logiciel d'édition d'image et créez une image de 256x256 pixels, puis convertissez-la en .ico.")
        
        return True
    except Exception as e:
        print(f"Erreur lors de la création des ressources: {str(e)}")
        return False

def create_autobot_package():
    """
    Crée un package AUTOBOT préemballé.
    
    Returns:
        bool: True si la création a réussi, False sinon
    """
    try:
        if not os.path.exists("autobot"):
            clone_repository()
        
        shutil.make_archive("autobot_package", "zip", "autobot")
        
        os.makedirs("resources", exist_ok=True)
        shutil.move("autobot_package.zip", "resources/autobot_package.zip")
        
        return True
    except Exception as e:
        print(f"Erreur lors de la création du package AUTOBOT: {str(e)}")
        return False
