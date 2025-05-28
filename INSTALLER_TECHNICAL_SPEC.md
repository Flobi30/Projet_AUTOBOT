# Spécification technique de l'installateur Windows AUTOBOT

## Vue d'ensemble

L'installateur Windows AUTOBOT est un exécutable unique (.exe) qui permet d'installer l'ensemble du système AUTOBOT en un seul clic, sans aucune intervention manuelle de l'utilisateur autre que la saisie des clés API via l'interface web après installation.

## Architecture de l'installateur

### Composants principaux

1. **Noyau d'installation** - Gère le processus d'installation global
2. **Interface graphique** - Fournit une interface utilisateur pendant l'installation
3. **Gestionnaire de dépendances** - Détecte et installe les dépendances requises
4. **Déployeur de code** - Extrait et configure le code source d'AUTOBOT
5. **Lanceur de serveur** - Démarre le serveur AUTOBOT et ouvre le navigateur

### Technologies utilisées

1. **PyInstaller** - Pour créer l'exécutable Windows à partir du code Python
2. **Tkinter** - Pour l'interface graphique de l'installateur
3. **Python Embeddable Package** - Version portable de Python incluse dans l'installateur
4. **Git** - Pour cloner le dépôt (ou version préemballée incluse dans l'installateur)
5. **NSIS** (optionnel) - Pour l'empaquetage final et la gestion des droits administrateur

## Flux d'installation

1. **Lancement de l'installateur** - L'utilisateur double-clique sur l'exécutable
2. **Vérification du système** - Détection des prérequis système
3. **Installation de Python** - Si nécessaire, déploiement du Python Embeddable Package
4. **Extraction du code** - Déploiement du code source d'AUTOBOT
5. **Installation des dépendances** - Installation automatique des packages Python requis
6. **Configuration** - Génération des fichiers de configuration avec valeurs par défaut
7. **Création des raccourcis** - Sur le bureau et dans le menu Démarrer
8. **Démarrage du serveur** - Lancement automatique du serveur AUTOBOT
9. **Ouverture du navigateur** - Redirection vers l'interface web pour la configuration des clés API

## Implémentation technique

### Structure des fichiers de l'installateur

```
installer/
├── src/
│   ├── installer_script.py     # Script principal
│   ├── installer_gui.py        # Interface graphique
│   ├── installer_utils.py      # Fonctions utilitaires
│   └── build_installer.py      # Script de construction
├── resources/
│   ├── python_embed/           # Python Embeddable Package
│   ├── autobot_source/         # Code source préemballé (optionnel)
│   ├── autobot_logo.ico        # Icône de l'application
│   └── autobot_banner.png      # Bannière pour l'installateur
└── dist/
    └── AUTOBOT_Installer.exe   # Exécutable final
```

### Détails d'implémentation

#### 1. Création de l'exécutable

```python
# build_installer.py
import PyInstaller.__main__
import os
import shutil

# Copier les ressources
shutil.copytree("resources", "build/resources")

# Créer l'exécutable avec PyInstaller
PyInstaller.__main__.run([
    "src/installer_script.py",
    "--name=AUTOBOT_Installer",
    "--onefile",
    "--windowed",
    "--icon=resources/autobot_logo.ico",
    "--add-data=resources;resources",
    "--hidden-import=tkinter",
    "--hidden-import=requests",
    "--hidden-import=git"
])
```

#### 2. Interface graphique

```python
# installer_gui.py (extrait)
import tkinter as tk
from tkinter import ttk
import webbrowser

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AUTOBOT Installer")
        self.root.geometry("600x400")
        
        # Bannière
        self.banner_img = tk.PhotoImage(file="resources/autobot_banner.png")
        self.banner = tk.Label(self.root, image=self.banner_img)
        self.banner.pack(pady=20)
        
        # Barre de progression
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        # Message de statut
        self.status_var = tk.StringVar()
        self.status_var.set("Préparation de l'installation...")
        self.status = tk.Label(self.root, textvariable=self.status_var)
        self.status.pack(pady=10)
```

#### 3. Installation de Python

```python
# installer_utils.py (extrait)
import os
import subprocess
import sys
import shutil

def check_python_installed():
    """Vérifie si Python est installé et à la bonne version."""
    try:
        output = subprocess.check_output(["python", "--version"], stderr=subprocess.STDOUT, text=True)
        version = output.strip().split()[1]
        major, minor, _ = version.split(".")
        if int(major) >= 3 and int(minor) >= 9:
            return True
    except:
        pass
    return False

def install_embedded_python():
    """Installe le Python Embeddable Package."""
    python_dir = os.path.join(os.environ["LOCALAPPDATA"], "AUTOBOT", "python")
    os.makedirs(python_dir, exist_ok=True)
    
    # Extraire Python Embeddable Package
    shutil.unpack_archive("resources/python_embed/python-3.10.0-embed-amd64.zip", python_dir)
    
    # Installer pip
    subprocess.run([os.path.join(python_dir, "python.exe"), "-m", "ensurepip"])
    
    return os.path.join(python_dir, "python.exe")
```

#### 4. Installation des dépendances

```python
# installer_utils.py (extrait)
def install_dependencies(python_exe, autobot_dir):
    """Installe les dépendances Python requises."""
    requirements_file = os.path.join(autobot_dir, "requirements.txt")
    subprocess.run([python_exe, "-m", "pip", "install", "-r", requirements_file])
```

#### 5. Démarrage du serveur et ouverture du navigateur

```python
# installer_utils.py (extrait)
def start_autobot_server(python_exe, autobot_dir):
    """Démarre le serveur AUTOBOT et ouvre le navigateur."""
    # Créer un script de démarrage
    start_script = os.path.join(autobot_dir, "start_autobot.bat")
    with open(start_script, "w") as f:
        f.write(f'@echo off\n"{python_exe}" "{os.path.join(autobot_dir, "src", "main.py")}"\n')
    
    # Démarrer le serveur
    subprocess.Popen([start_script], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # Attendre que le serveur démarre
    import time
    time.sleep(5)
    
    # Ouvrir le navigateur
    webbrowser.open("http://localhost:8000")
    
    return "http://localhost:8000"
```

## Gestion des clés API

L'installateur ne demande pas les clés API pendant l'installation. Celles-ci sont configurées exclusivement via l'interface web après installation, en utilisant l'endpoint `/setup` dans `router_clean.py`.

```python
# Extrait de router_clean.py
@app.post("/setup")
async def setup(request: Request, api_keys: dict = Body(...)):
    """Configure les clés API via l'interface web."""
    try:
        # Enregistrer les clés API
        with open("config/api_keys.json", "w") as f:
            json.dump(api_keys, f, indent=4)
        
        # Démarrer les backtests automatiquement
        start_backtests()
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## Création de l'installateur

Pour créer l'installateur Windows, exécutez le script `build_installer.py` :

```bash
python src/build_installer.py
```

L'exécutable sera créé dans le dossier `dist` sous le nom `AUTOBOT_Installer.exe`.

## Utilisation de l'installateur

1. Double-cliquez sur `AUTOBOT_Installer.exe`
2. Suivez les instructions à l'écran (minimal, car tout est automatique)
3. Une fois l'installation terminée, le navigateur s'ouvrira automatiquement
4. Configurez vos clés API via l'interface web
5. Le système démarrera automatiquement les backtests après configuration

## Avantages de cette approche

1. **Installation en un clic** - Aucune commande à taper
2. **Indépendance** - Fonctionne même sans Python préinstallé
3. **Sécurité** - Les clés API sont saisies uniquement via l'interface web sécurisée
4. **Simplicité** - Expérience utilisateur intuitive et sans friction
5. **Portabilité** - Fonctionne sur toutes les versions de Windows (7, 8, 10, 11)
