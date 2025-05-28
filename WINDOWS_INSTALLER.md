# AUTOBOT - Installateur Windows en un clic

Ce document explique comment créer et utiliser l'installateur Windows en un clic pour AUTOBOT.

## Vue d'ensemble

L'installateur Windows (.exe) permet d'installer AUTOBOT en un seul clic, sans aucune commande à taper. Il gère automatiquement :

- La vérification et l'installation de Python
- Le téléchargement du code source d'AUTOBOT
- L'installation de toutes les dépendances
- La configuration de l'environnement
- Le démarrage du serveur
- L'ouverture du navigateur sur l'interface web

L'utilisateur n'a qu'à saisir ses clés API via l'interface web après l'installation.

## Prérequis pour créer l'installateur

Pour créer l'installateur Windows, vous aurez besoin de :

1. Windows 10 ou 11
2. Python 3.9+ installé
3. Git installé
4. Connexion Internet

## Étapes pour créer l'installateur

1. Clonez le dépôt AUTOBOT :
   ```
   git clone https://github.com/Flobi30/Projet_AUTOBOT.git
   cd Projet_AUTOBOT
   ```

2. Installez les dépendances nécessaires :
   ```
   pip install pyinstaller pillow
   ```

3. Exécutez le script de construction :
   ```
   python src/build_installer.py
   ```

4. L'installateur sera créé dans le dossier `dist` sous le nom `AUTOBOT_Installer.exe`

## Utilisation de l'installateur

1. Double-cliquez sur `AUTOBOT_Installer.exe`
2. Suivez les instructions à l'écran
3. Une fois l'installation terminée, le navigateur s'ouvrira automatiquement sur l'interface web d'AUTOBOT
4. Configurez vos clés API via l'interface web

## Structure des fichiers de l'installateur

- `src/installer_script.py` : Script principal de l'installateur
- `src/installer_gui.py` : Interface graphique Tkinter
- `src/installer_utils.py` : Fonctions utilitaires
- `src/build_installer.py` : Script de construction de l'installateur

## Fonctionnement technique

L'installateur utilise les technologies suivantes :

1. **PyInstaller** pour créer l'exécutable Windows à partir du script Python
2. **Tkinter** pour l'interface graphique pendant l'installation
3. **Python Embeddable Package** inclus dans l'exécutable pour éviter la dépendance à une installation Python existante
4. **Git** pour cloner le dépôt (ou utilise une version préemballée incluse dans l'installateur)

Le processus d'installation se déroule comme suit :

1. L'utilisateur lance l'exécutable
2. L'installateur vérifie si Python est installé, sinon il déploie le Python Embeddable Package inclus
3. Il clone le dépôt AUTOBOT ou déploie la version préemballée
4. Il installe toutes les dépendances requises
5. Il crée les fichiers de configuration nécessaires
6. Il crée des raccourcis sur le bureau et dans le menu Démarrer
7. Il démarre le serveur AUTOBOT
8. Il ouvre le navigateur sur l'interface web

## Configuration des clés API

La configuration des clés API se fait exclusivement via l'interface web après l'installation. L'endpoint `/setup` dans `router_clean.py` permet d'envoyer les clés API via une requête POST, et les backtests démarrent automatiquement après configuration.

## Personnalisation de l'installateur

Vous pouvez personnaliser l'installateur en modifiant les fichiers suivants :

- `resources/autobot_banner.png` : Bannière affichée pendant l'installation
- `resources/autobot_logo.ico` : Icône de l'application
- `src/installer_gui.py` : Apparence de l'interface graphique
- `src/installer_utils.py` : Comportement de l'installateur

## Déploiement sur un serveur

Pour déployer AUTOBOT sur un serveur Hetzner CX51 ou similaire, vous pouvez :

1. Télécharger l'installateur sur le serveur
2. Exécuter l'installateur avec `wine AUTOBOT_Installer.exe` (si Wine est installé)
3. Ou utiliser le script d'installation Linux fourni dans le dépôt

## Dépannage

Si vous rencontrez des problèmes lors de la création ou de l'utilisation de l'installateur :

1. Vérifiez que vous avez les droits administrateur
2. Assurez-vous que votre antivirus ne bloque pas l'exécution
3. Vérifiez que vous avez une connexion Internet active
4. Consultez les logs dans le dossier `%TEMP%\autobot_installer_log.txt`

Pour toute question ou problème, veuillez ouvrir une issue sur le dépôt GitHub.
