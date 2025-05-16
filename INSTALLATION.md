# Guide d'Installation d'AUTOBOT

Ce guide vous aidera à installer et configurer AUTOBOT sur différentes plateformes.

## Prérequis

- Python 3.9+ 
- pip (gestionnaire de paquets Python)
- Git
- Accès à Internet
- Clé API pour les plateformes d'échange (pour le trading)

## Installation Automatique (Recommandée)

AUTOBOT dispose d'un installateur automatique qui configure tout pour vous.

```bash
# Télécharger le projet
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Exécuter l'installateur
python installer.py
```

L'installateur vous guidera à travers les étapes suivantes:
1. Vérification des prérequis
2. Installation des dépendances
3. Configuration des clés API
4. Création du fichier de configuration
5. Installation des modules optionnels

## Installation Manuelle

Si vous préférez une installation manuelle:

```bash
# Télécharger le projet
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Créer un environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Installer le package en mode développement
pip install -e .
```

## Configuration

Après l'installation, vous devez configurer AUTOBOT:

1. Créez un fichier `.env` à la racine du projet avec les informations suivantes:

```
# Clés API pour les plateformes d'échange
BINANCE_API_KEY=votre_clé_api
BINANCE_API_SECRET=votre_clé_secrète

# Configuration de la base de données
DB_HOST=localhost
DB_PORT=5432
DB_NAME=autobot
DB_USER=postgres
DB_PASSWORD=votre_mot_de_passe

# Configuration de sécurité
JWT_SECRET=votre_clé_secrète_jwt
LICENSE_KEY=votre_clé_de_licence
```

2. Exécutez le script de configuration:

```bash
python -m autobot.setup
```

## Démarrage

Pour démarrer AUTOBOT:

```bash
# Démarrer l'application principale
python -m autobot.main
```

L'interface web sera accessible à l'adresse: http://localhost:8000

## Configuration Docker (Optionnel)

AUTOBOT peut également être exécuté dans Docker:

```bash
# Construire l'image
docker-compose build

# Démarrer les services
docker-compose up -d
```

## Modes d'Exécution

AUTOBOT dispose de plusieurs modes d'exécution:

- **Mode Standard**: Équilibre entre performance et sécurité
  ```bash
  python -m autobot.main --mode standard
  ```

- **Mode Turbo**: Priorité à la performance
  ```bash
  python -m autobot.main --mode turbo
  ```

- **Mode Ghost**: Priorité à l'indétectabilité
  ```bash
  python -m autobot.main --mode ghost
  ```

## Dépannage

Si vous rencontrez des problèmes:

1. Vérifiez les logs dans le dossier `logs/`
2. Assurez-vous que toutes les dépendances sont installées
3. Vérifiez que les clés API sont correctes
4. Consultez la documentation dans le dossier `docs/`

## Support

Pour obtenir de l'aide:

- Consultez la documentation dans le dossier `docs/`
- Ouvrez une issue sur GitHub
- Contactez l'équipe de support

## Mise à Jour

Pour mettre à jour AUTOBOT:

```bash
git pull
pip install -r requirements.txt
python -m autobot.setup --update
```
