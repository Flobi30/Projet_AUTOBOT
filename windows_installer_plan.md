# Plan d'implémentation de l'installateur Windows pour AUTOBOT

## Vue d'ensemble

Ce document détaille l'implémentation d'un installateur Windows (.exe) en un seul clic pour AUTOBOT, permettant une installation complètement automatisée avec configuration des clés API via l'interface web.

## Technologies utilisées

1. **PyInstaller** - Pour créer l'exécutable Windows à partir du script Python
2. **Tkinter** - Pour l'interface graphique pendant l'installation
3. **Python Embeddable Package** - Pour inclure Python dans l'exécutable
4. **NSIS (Nullsoft Scriptable Install System)** - Pour l'empaquetage final

## Structure du projet d'installateur

```
autobot_windows_installer/
├── installer_script.py       # Script principal de l'installateur
├── installer_gui.py          # Interface graphique Tkinter
├── installer_utils.py        # Fonctions utilitaires
├── resources/                # Ressources pour l'installateur
│   ├── autobot_logo.ico      # Icône de l'application
│   ├── autobot_banner.png    # Bannière pour l'interface
│   └── python_embedded.zip   # Python embeddable package
└── nsis/                     # Scripts NSIS
    └── autobot_installer.nsi # Script NSIS pour l'empaquetage
```

## Fonctionnalités de l'installateur

1. **Détection et installation automatique de Python**
   - Vérifie si Python 3.9+ est installé
   - Si non, déploie le Python Embeddable Package inclus

2. **Installation automatique des dépendances**
   - Installe pip si nécessaire
   - Installe toutes les dépendances requises

3. **Clonage du dépôt AUTOBOT**
   - Clone le dépôt depuis GitHub
   - Ou déploie une version préemballée incluse dans l'installateur

4. **Configuration de l'environnement**
   - Crée les fichiers de configuration nécessaires
   - Génère des clés de sécurité aléatoires

5. **Création de raccourcis**
   - Crée un raccourci sur le bureau
   - Ajoute AUTOBOT au menu Démarrer

6. **Démarrage automatique**
   - Lance le serveur AUTOBOT
   - Ouvre le navigateur sur l'interface web

## Implémentation détaillée

### 1. Script principal de l'installateur (installer_script.py)

```python
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
    # Initialiser l'interface graphique
    root = tk.Tk()
    app = InstallerGUI(root)
    
    # Démarrer le processus d'installation dans un thread séparé
    install_thread = threading.Thread(target=run_installation, args=(app,))
    install_thread.daemon = True
    install_thread.start()
    
    root.mainloop()

def run_installation(app):
    # Mettre à jour l'interface avec le statut
    app.update_status("Vérification des prérequis système...")
    
    # 1. Vérifier si Python est installé
    if not check_python_installed():
        app.update_status("Installation de Python...")
        install_embedded_python()
    
    # 2. Cloner le dépôt
    app.update_status("Téléchargement d'AUTOBOT...")
    app.update_progress(20)
    clone_repository()
    
    # 3. Installer les dépendances
    app.update_status("Installation des dépendances...")
    app.update_progress(40)
    install_dependencies()
    
    # 4. Créer les fichiers de configuration
    app.update_status("Configuration d'AUTOBOT...")
    app.update_progress(60)
    jwt_secret = generate_secure_key(32)
    admin_password = generate_secure_key(12)
    create_config_files(jwt_secret, admin_password)
    
    # 5. Créer les raccourcis
    app.update_status("Création des raccourcis...")
    app.update_progress(80)
    create_shortcuts()
    
    # 6. Démarrer AUTOBOT
    app.update_status("Démarrage d'AUTOBOT...")
    app.update_progress(100)
    server_url = start_autobot_server()
    
    # 7. Ouvrir le navigateur
    app.installation_complete(server_url, admin_password)

if __name__ == "__main__":
    main()
```

### 2. Interface graphique (installer_gui.py)

```python
import tkinter as tk
from tkinter import ttk
import webbrowser

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AUTOBOT Installer")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        # Centrer la fenêtre
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 600) // 2
        y = (screen_height - 400) // 2
        self.root.geometry(f"600x400+{x}+{y}")
        
        # Bannière
        self.banner_img = tk.PhotoImage(file="resources/autobot_banner.png")
        self.banner = tk.Label(self.root, image=self.banner_img)
        self.banner.pack(pady=20)
        
        # Titre
        self.title = tk.Label(self.root, text="Installation d'AUTOBOT", font=("Arial", 16, "bold"))
        self.title.pack(pady=10)
        
        # Message de statut
        self.status_var = tk.StringVar()
        self.status_var.set("Préparation de l'installation...")
        self.status = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 10))
        self.status.pack(pady=10)
        
        # Barre de progression
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        # Zone de message final (initialement cachée)
        self.final_frame = tk.Frame(self.root)
        self.final_message = tk.Label(self.final_frame, text="", font=("Arial", 10), justify=tk.LEFT, wraplength=500)
        self.open_browser_btn = tk.Button(self.final_frame, text="Ouvrir l'interface web", command=self.open_browser)
        
        self.server_url = None
    
    def update_status(self, message):
        self.status_var.set(message)
        self.root.update()
    
    def update_progress(self, value):
        self.progress["value"] = value
        self.root.update()
    
    def installation_complete(self, server_url, admin_password):
        self.server_url = server_url
        
        # Afficher le message final
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
        self.open_browser_btn.pack(pady=10)
        
        # Masquer les éléments précédents
        self.status.pack_forget()
        self.progress.pack_forget()
    
    def open_browser(self):
        if self.server_url:
            webbrowser.open(self.server_url)
```

### 3. Fonctions utilitaires (installer_utils.py)

```python
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
from pathlib import Path

def check_python_installed():
    """Vérifie si Python 3.9+ est installé."""
    try:
        # Vérifier la version de Python
        version = subprocess.run(
            ["python", "--version"], 
            capture_output=True, 
            text=True
        ).stdout
        
        # Extraire la version
        import re
        match = re.search(r"Python (\d+)\.(\d+)\.(\d+)", version)
        if match:
            major, minor, _ = map(int, match.groups())
            return major >= 3 and minor >= 9
        
        return False
    except:
        return False

def install_embedded_python():
    """Installe le Python Embeddable Package inclus."""
    # Extraire le Python embeddable package
    with zipfile.ZipFile("resources/python_embedded.zip", "r") as zip_ref:
        zip_ref.extractall("python_embedded")
    
    # Ajouter Python au PATH pour cette session
    os.environ["PATH"] = os.path.abspath("python_embedded") + os.pathsep + os.environ["PATH"]
    
    # Installer pip
    subprocess.run(
        ["python_embedded/python.exe", "resources/get-pip.py"],
        check=True
    )

def clone_repository():
    """Clone le dépôt AUTOBOT ou déploie la version préemballée."""
    if os.path.exists("resources/autobot_package.zip"):
        # Utiliser la version préemballée
        with zipfile.ZipFile("resources/autobot_package.zip", "r") as zip_ref:
            zip_ref.extractall("autobot")
    else:
        # Cloner depuis GitHub
        subprocess.run(
            ["git", "clone", "https://github.com/Flobi30/Projet_AUTOBOT.git", "autobot"],
            check=True
        )

def install_dependencies():
    """Installe toutes les dépendances requises."""
    # Installer les dépendances Python
    subprocess.run(
        ["python", "-m", "pip", "install", "--upgrade", "pip"],
        check=True
    )
    
    # Installer les dépendances depuis requirements.txt
    subprocess.run(
        ["python", "-m", "pip", "install", "-r", "autobot/requirements.txt"],
        check=True
    )

def generate_secure_key(length):
    """Génère une clé sécurisée aléatoire."""
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

def create_config_files(jwt_secret, admin_password):
    """Crée les fichiers de configuration nécessaires."""
    # Créer le répertoire de configuration
    os.makedirs("autobot/config", exist_ok=True)
    
    # Créer le fichier .env
    with open("autobot/.env", "w") as f:
        f.write(f"AUTOBOT_JWT_SECRET={jwt_secret}\n")
        f.write(f"AUTOBOT_ADMIN_PASSWORD={admin_password}\n")
        f.write("AUTOBOT_MAX_INSTANCES=100\n")
        f.write("AUTOBOT_DEPLOYMENT_TYPE=local\n")

def create_shortcuts():
    """Crée les raccourcis sur le bureau et dans le menu Démarrer."""
    # Chemin vers le script de démarrage
    start_script = os.path.abspath("autobot/start_autobot.bat")
    
    # Créer le script de démarrage
    with open(start_script, "w") as f:
        f.write("@echo off\n")
        f.write("cd %~dp0\n")
        f.write("python -m src.autobot.main\n")
    
    # Créer le raccourci sur le bureau
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    shortcut_path = os.path.join(desktop, "AUTOBOT.lnk")
    
    # Utiliser PowerShell pour créer le raccourci
    ps_command = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
    $Shortcut.TargetPath = "{start_script}"
    $Shortcut.IconLocation = "{os.path.abspath('resources/autobot_logo.ico')}"
    $Shortcut.Save()
    """
    
    subprocess.run(["powershell", "-Command", ps_command], check=True)

def start_autobot_server():
    """Démarre le serveur AUTOBOT et retourne l'URL."""
    # Démarrer le serveur dans un processus séparé
    subprocess.Popen(
        ["python", "-m", "src.autobot.main"],
        cwd="autobot",
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    
    # Attendre que le serveur démarre
    time.sleep(5)
    
    # Retourner l'URL
    return "http://localhost:8000"
```

### 4. Script NSIS (autobot_installer.nsi)

```nsi
; AUTOBOT Installer Script
; Nullsoft Scriptable Install System script

; Définir le nom et la version
!define APPNAME "AUTOBOT"
!define APPVERSION "1.0.0"
!define PUBLISHER "Flobi30"

; Inclure les bibliothèques modernes
!include "MUI2.nsh"

; Définir les métadonnées de l'installateur
Name "${APPNAME} ${APPVERSION}"
OutFile "AUTOBOT_Installer.exe"
InstallDir "$PROGRAMFILES\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "Install_Dir"
RequestExecutionLevel admin

; Pages de l'interface
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Langues
!insertmacro MUI_LANGUAGE "French"

; Section d'installation principale
Section "Installation" SecInstall
  SetOutPath "$INSTDIR"
  
  ; Fichiers à inclure dans l'installateur
  File /r "dist\*.*"
  
  ; Créer les raccourcis
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\autobot_installer.exe"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\autobot_installer.exe"
  
  ; Écrire les informations de désinstallation
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Exécuter l'installateur Python
  ExecWait '"$INSTDIR\autobot_installer.exe"'
SectionEnd

; Section de désinstallation
Section "Uninstall"
  ; Supprimer les fichiers
  RMDir /r "$INSTDIR"
  
  ; Supprimer les raccourcis
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  
  ; Supprimer les clés de registre
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKLM "Software\${APPNAME}"
SectionEnd
```

## Processus de création de l'exécutable

1. **Préparation des ressources**
   - Télécharger le Python Embeddable Package
   - Créer les ressources graphiques (logo, bannière)

2. **Développement des scripts Python**
   - Implémenter les scripts décrits ci-dessus
   - Tester sur différentes versions de Windows

3. **Compilation avec PyInstaller**
   ```
   pyinstaller --onefile --windowed --icon=resources/autobot_logo.ico --add-data "resources/*;resources/" installer_script.py
   ```

4. **Empaquetage avec NSIS**
   - Compiler le script NSIS pour créer l'installateur final
   ```
   makensis autobot_installer.nsi
   ```

5. **Tests d'installation**
   - Tester sur des machines virtuelles Windows propres
   - Vérifier que toutes les fonctionnalités marchent correctement

## Flux d'utilisation

1. L'utilisateur télécharge et exécute `AUTOBOT_Installer.exe`
2. L'installateur vérifie et installe les prérequis
3. L'interface graphique affiche la progression de l'installation
4. Une fois l'installation terminée, le serveur AUTOBOT démarre automatiquement
5. Le navigateur s'ouvre sur l'interface web
6. L'utilisateur peut alors configurer ses clés API via l'interface web

## Avantages de cette approche

1. **Installation en un seul clic** - Aucune commande à taper
2. **Gestion automatique des dépendances** - Python et toutes les bibliothèques sont inclus
3. **Interface graphique intuitive** - Expérience utilisateur familière pour Windows
4. **Configuration via interface web** - Les clés API sont saisies uniquement via l'interface web
5. **Démarrage automatique** - Le serveur et le navigateur démarrent automatiquement

## Prochaines étapes

1. Implémenter les scripts Python décrits
2. Créer les ressources graphiques
3. Tester sur différentes versions de Windows
4. Créer l'exécutable final avec PyInstaller et NSIS
