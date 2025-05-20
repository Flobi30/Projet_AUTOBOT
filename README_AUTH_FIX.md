# Correction du problème d'authentification AUTOBOT

Ce document explique comment résoudre les problèmes d'authentification "Not authenticated" sur le serveur Hetzner exécutant AUTOBOT.

## Problème

Le problème est causé par deux facteurs principaux :

1. **Chemin relatif vs absolu** : Le `UserManager` est initialisé avec un chemin relatif "users.json", ce qui peut causer des problèmes selon le répertoire de travail.

2. **Absence d'utilisateur par défaut** : Aucun utilisateur administrateur n'est créé automatiquement lorsque `users.json` n'existe pas ou est vide.

## Solution

La solution consiste à créer une classe `ModifiedUserManager` qui étend `UserManager` pour :

1. Utiliser des chemins absolus pour les fichiers de configuration
2. Créer automatiquement un utilisateur administrateur par défaut à partir de `auth_config.json`

## Instructions d'installation

### Option 1 : Utiliser le script automatique

1. Téléchargez le script `update_auth_files.sh` sur votre serveur Hetzner
2. Rendez-le exécutable : `chmod +x update_auth_files.sh`
3. Exécutez-le : `./update_auth_files.sh`
4. Suivez les instructions à l'écran

### Option 2 : Mise à jour manuelle

1. **Créer le fichier ModifiedUserManager**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/auth/modified_user_manager.py
```

Copiez le contenu du fichier `modified_user_manager.py` fourni dans le script.

2. **Mettre à jour le fichier __init__.py**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/auth/__init__.py
```

Ajoutez l'import de `ModifiedUserManager` et mettez à jour `__all__`.

3. **Mettre à jour le fichier config.py**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/src/autobot/autobot_security/config.py
```

Remplacez le contenu par celui fourni dans le script.

4. **Mettre à jour main_enhanced.py**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/src/autobot/main_enhanced.py
```

Ajoutez l'import de `ModifiedUserManager` et remplacez `user_manager = UserManager()` par `user_manager = ModifiedUserManager()`.

5. **Mettre à jour main.py**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/main.py
```

Remplacez le contenu par celui fourni dans le script.

6. **Vérifier auth_config.json**

```bash
sudo nano /home/autobot/Projet_AUTOBOT/config/auth_config.json
```

Assurez-vous qu'il contient tous les paramètres nécessaires.

## Redémarrage et vérification

1. **Redémarrer le service AUTOBOT**

```bash
sudo supervisorctl restart autobot
```

2. **Vérifier les logs**

```bash
sudo tail -f /var/log/autobot/autobot.log
```

Recherchez des messages comme :
- "✅ Système d'authentification initialisé avec succès"
- "Création de l'utilisateur administrateur par défaut : admin"
- "Utilisateur administrateur créé avec succès."

3. **Tester l'accès à l'interface utilisateur**

Visitez l'URL de votre application (http://144.76.16.177 ou l'IP correspondante) et connectez-vous avec les identifiants définis dans auth_config.json.

## Dépannage

Si vous rencontrez des erreurs, vérifiez les logs d'erreur :

```bash
sudo tail -f /var/log/autobot/autobot_error.log
```

## Détails techniques

La solution résout plusieurs problèmes avec le système d'authentification actuel :

1. **Chemin relatif vs absolu** : La version modifiée utilise des chemins absolus pour éviter les problèmes liés au répertoire de travail.

2. **Création d'un utilisateur administrateur par défaut** : Le `ModifiedUserManager` crée automatiquement un utilisateur administrateur à partir des informations dans `auth_config.json` si `users.json` n'existe pas ou est vide.

3. **Cohérence de la configuration** : Tous les paramètres d'authentification sont maintenant centralisés dans `auth_config.json`, y compris les informations de l'utilisateur administrateur par défaut.

4. **Suppression de la dépendance openhands** : Le fichier `main.py` a été réécrit pour éliminer la dépendance à openhands tout en maintenant les fonctionnalités d'AutobotKernel.
