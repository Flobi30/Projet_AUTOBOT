"""
Exemple de code pour l'installateur Windows AUTOBOT

Ce script montre comment implémenter l'installateur Windows en un clic
pour AUTOBOT, en utilisant PyInstaller pour créer l'exécutable.
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import threading
import time
import webbrowser
import shutil
import random
import string
import json
import tempfile
import zipfile
import urllib.request
from pathlib import Path

PYTHON_VERSION = "3.10.0"
AUTOBOT_REPO = "https://github.com/Flobi30/Projet_AUTOBOT.git"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

class InstallerGUI:
    """Interface graphique pour l'installateur AUTOBOT."""
    
    def __init__(self, root):
        """Initialise l'interface graphique."""
        self.root = root
        self.root.title("AUTOBOT Installer")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 600) // 2
        y = (screen_height - 400) // 2
        self.root.geometry(f"600x400+{x}+{y}")
        
        try:
            self.banner_img = tk.PhotoImage(file="resources/autobot_banner.png")
            self.banner = tk.Label(self.root, image=self.banner_img)
            self.banner.pack(pady=20)
        except:
            self.title_banner = tk.Label(self.root, text="AUTOBOT", font=("Arial", 24, "bold"))
            self.title_banner.pack(pady=20)
        
        self.title = tk.Label(self.root, text="Installation d'AUTOBOT", font=("Arial", 16, "bold"))
        self.title.pack(pady=10)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Préparation de l'installation...")
        self.status = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 10))
        self.status.pack(pady=10)
        
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        self.final_frame = tk.Frame(self.root)
        self.final_message = tk.Label(self.final_frame, text="", font=("Arial", 10), justify=tk.LEFT, wraplength=500)
        self.open_browser_btn = tk.Button(self.final_frame, text="Ouvrir l'interface web", command=self.open_browser)
        self.exit_btn = tk.Button(self.final_frame, text="Fermer l'installateur", command=self.root.destroy)
        
        self.server_url = None
    
    def update_status(self, message):
        """Met à jour le message de statut."""
        self.status_var.set(message)
        self.root.update()
    
    def update_progress(self, value):
        """Met à jour la barre de progression."""
        self.progress["value"] = value
        self.root.update()
    
    def installation_complete(self, server_url, admin_password):
        """Affiche le message de fin d'installation."""
        self.server_url = server_url
        
        self.final_message.config(text=f"""
Installation terminée avec succès !

AUTOBOT est maintenant installé et prêt à être utilisé.

Accédez à l'interface web pour configurer vos clés API :
{server_url}

Nom d'utilisateur : admin
Mot de passe : {admin_password}

Cliquez sur le bouton ci-dessous pour ouvrir l'interface web.
        """)
        
        self.final_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.final_message.pack(pady=10)
        self.open_browser_btn.pack(pady=5)
        self.exit_btn.pack(pady=5)
        
        self.status.pack_forget()
        self.progress.pack_forget()
        
        self.open_browser()
    
    def open_browser(self):
        """Ouvre le navigateur sur l'interface web d'AUTOBOT."""
        if self.server_url:
            webbrowser.open(self.server_url)

class InstallerUtils:
    """Fonctions utilitaires pour l'installateur."""
    
    @staticmethod
    def generate_password(length=12):
        """Génère un mot de passe aléatoire."""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choice(chars) for _ in range(length))
    
    @staticmethod
    def check_python_installed():
        """Vérifie si Python est installé et à la bonne version."""
        try:
            output = subprocess.check_output(["python", "--version"], stderr=subprocess.STDOUT, text=True)
            version = output.strip().split()[1]
            major, minor, _ = version.split(".")
            if int(major) >= 3 and int(minor) >= 9:
                return True, output.strip()
        except:
            pass
        return False, None
    
    @staticmethod
    def install_embedded_python(install_dir):
        """Installe le Python Embeddable Package."""
        python_dir = os.path.join(install_dir, "python")
        os.makedirs(python_dir, exist_ok=True)
        
        python_zip = os.path.join(tempfile.gettempdir(), "python_embed.zip")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, python_zip)
        
        with zipfile.ZipFile(python_zip, 'r') as zip_ref:
            zip_ref.extractall(python_dir)
        
        get_pip = os.path.join(python_dir, "get-pip.py")
        urllib.request.urlretrieve(GET_PIP_URL, get_pip)
        
        pth_files = [f for f in os.listdir(python_dir) if f.endswith("._pth")]
        if pth_files:
            pth_file = os.path.join(python_dir, pth_files[0])
            with open(pth_file, 'r') as f:
                content = f.read()
            
            content = content.replace("#import site", "import site")
            
            with open(pth_file, 'w') as f:
                f.write(content)
        
        subprocess.run([os.path.join(python_dir, "python.exe"), get_pip])
        
        return os.path.join(python_dir, "python.exe")
    
    @staticmethod
    def clone_repository(install_dir, python_exe):
        """Clone le dépôt AUTOBOT."""
        autobot_dir = os.path.join(install_dir, "autobot")
        
        subprocess.run([python_exe, "-m", "pip", "install", "gitpython"])
        
        import git
        git.Repo.clone_from(AUTOBOT_REPO, autobot_dir)
        
        return autobot_dir
    
    @staticmethod
    def install_dependencies(python_exe, autobot_dir):
        """Installe les dépendances Python requises."""
        requirements_file = os.path.join(autobot_dir, "requirements.txt")
        subprocess.run([python_exe, "-m", "pip", "install", "-r", requirements_file])
    
    @staticmethod
    def create_config_files(autobot_dir, admin_password):
        """Crée les fichiers de configuration nécessaires."""
        config_dir = os.path.join(autobot_dir, "config")
        os.makedirs(config_dir, exist_ok=True)
        
        config = {
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "debug": False
            },
            "security": {
                "jwt_secret": ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32)),
                "admin_password": admin_password
            },
            "database": {
                "url": "sqlite:///./autobot.db"
            }
        }
        
        with open(os.path.join(config_dir, "config.json"), 'w') as f:
            json.dump(config, f, indent=4)
        
        with open(os.path.join(config_dir, "api_keys.json"), 'w') as f:
            json.dump({}, f, indent=4)
    
    @staticmethod
    def create_shortcuts(install_dir, autobot_dir, python_exe):
        """Crée des raccourcis sur le bureau et dans le menu Démarrer."""
        start_script = os.path.join(autobot_dir, "start_autobot.bat")
        with open(start_script, "w") as f:
            f.write(f'@echo off\n"{python_exe}" "{os.path.join(autobot_dir, "src", "main.py")}"\n')
        
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "AUTOBOT.lnk")
        
        try:
            import winshell
            from win32com.client import Dispatch
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = start_script
            shortcut.WorkingDirectory = autobot_dir
            shortcut.IconLocation = os.path.join(install_dir, "resources", "autobot_logo.ico")
            shortcut.save()
        except:
            shutil.copy(start_script, desktop)
    
    @staticmethod
    def start_autobot_server(autobot_dir, python_exe):
        """Démarre le serveur AUTOBOT et ouvre le navigateur."""
        start_script = os.path.join(autobot_dir, "start_autobot.bat")
        
        subprocess.Popen([start_script], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        time.sleep(5)
        
        return "http://localhost:8000"

def run_installation(app):
    """Exécute le processus d'installation complet."""
    install_dir = os.path.join(os.environ["LOCALAPPDATA"], "AUTOBOT")
    os.makedirs(install_dir, exist_ok=True)
    
    app.update_status("Vérification des prérequis système...")
    app.update_progress(10)
    
    python_installed, python_version = InstallerUtils.check_python_installed()
    if python_installed:
        app.update_status(f"Python détecté: {python_version}")
        python_exe = "python"
    else:
        app.update_status("Installation de Python...")
        python_exe = InstallerUtils.install_embedded_python(install_dir)
    
    app.update_status("Téléchargement d'AUTOBOT...")
    app.update_progress(30)
    autobot_dir = InstallerUtils.clone_repository(install_dir, python_exe)
    
    app.update_status("Installation des dépendances...")
    app.update_progress(50)
    InstallerUtils.install_dependencies(python_exe, autobot_dir)
    
    app.update_status("Configuration d'AUTOBOT...")
    app.update_progress(70)
    admin_password = InstallerUtils.generate_password()
    InstallerUtils.create_config_files(autobot_dir, admin_password)
    
    app.update_status("Création des raccourcis...")
    app.update_progress(85)
    InstallerUtils.create_shortcuts(install_dir, autobot_dir, python_exe)
    
    app.update_status("Démarrage d'AUTOBOT...")
    app.update_progress(95)
    server_url = InstallerUtils.start_autobot_server(autobot_dir, python_exe)
    
    app.update_progress(100)
    app.installation_complete(server_url, admin_password)

def main():
    """Fonction principale de l'installateur."""
    root = tk.Tk()
    app = InstallerGUI(root)
    
    install_thread = threading.Thread(target=run_installation, args=(app,))
    install_thread.daemon = True
    install_thread.start()
    
    root.mainloop()

if __name__ == "__main__":
    main()
