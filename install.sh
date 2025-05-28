#!/bin/bash

echo "🤖 Installation d'AUTOBOT - Framework de Trading et RL 🤖"
echo "========================================================="

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 n'est pas installé. Installation..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
else
    echo "✅ Python3 est déjà installé"
fi

echo "🔧 Création de l'environnement virtuel..."
python3 -m venv venv
source venv/bin/activate

echo "📦 Installation des dépendances..."
pip install -r requirements.txt

echo "🔑 Configuration des clés API..."
python -c "
import json
import os
from getpass import getpass

config_dir = 'config'
os.makedirs(config_dir, exist_ok=True)
config_file = os.path.join(config_dir, 'api_keys.json')

keys = {}
for exchange in ['binance', 'coinbase', 'kraken']:
    print(f'Configuration pour {exchange.upper()}:')
    api_key = getpass(f'Entrez votre clé API {exchange}: ')
    api_secret = getpass(f'Entrez votre secret API {exchange}: ')
    if api_key and api_secret:
        keys[exchange] = {'api_key': api_key, 'api_secret': api_secret}

with open(config_file, 'w') as f:
    json.dump(keys, f)
print(f'✅ Clés API sauvegardées dans {config_file}')
"

echo "🧪 Lancement des backtests..."
python run_backtests.py

echo "✅ Installation terminée avec succès!"
echo "🚀 Pour lancer l'application, exécutez: python -m src.autobot.main"
