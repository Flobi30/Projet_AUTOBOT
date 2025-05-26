# AUTOBOT - Trading and Automation Framework

![AUTOBOT Logo](src/autobot/ui/static/img/logo.png)

## Description

AUTOBOT est un framework complet pour le trading automatisé, l'apprentissage par renforcement et l'orchestration multi-agents. Il intègre des fonctionnalités avancées pour le trading algorithmique, la gestion des risques, l'apprentissage automatique, et la gestion d'inventaire e-commerce.

## Architecture

Le projet est structuré en plusieurs modules principaux :

### 1. SuperAGI - Orchestrateur Principal

- **AutobotMaster** : Agent orchestrateur principal qui pilote tous les composants
- **Interface conversationnelle** : Contrôle de tous les modules via langage naturel
- **Intégration API** : Mapping des endpoints FastAPI vers des outils SuperAGI
- **Workflows automatisés** : Exécution de séquences d'actions complexes

### 2. Module de Trading

- **Fournisseur CCXT amélioré** : Intégration complète avec les échanges de cryptomonnaies
- **Gestionnaire de risque avancé** : Dimensionnement des positions, protection contre les drawdowns
- **Exécution des ordres** : Système robuste pour l'exécution des stratégies
- **Stratégies de trading** : Framework extensible pour implémenter diverses stratégies

### 2. Module d'Apprentissage par Renforcement (RL)

- **Agent RL** : Implémentation d'agents d'apprentissage par renforcement
- **Environnement de trading** : Simulation du marché pour l'entraînement des agents
- **Système d'entraînement** : Boucle d'apprentissage avec sauvegarde et chargement des modèles

### 3. Module de Sécurité

- **Authentification OAuth2/JWT** : Système sécurisé de gestion des sessions avec tokens JWT HS256
- **Protection CSRF** : Sécurisation des formulaires contre les attaques Cross-Site Request Forgery
- **Gestion des utilisateurs** : Création, authentification et gestion des utilisateurs
- **Système de licences** : Contrôle d'accès basé sur des licences avec vérification via LICENSE_KEY
- **Configuration centralisée** : Variables sensibles stockées uniquement dans le fichier .env

### 4. Orchestrateur Multi-Agent

- **Gestion des agents** : Création et supervision d'agents autonomes
- **Communication inter-agents** : Système de messagerie pour la collaboration
- **Allocation des ressources** : Distribution intelligente des tâches

### 5. Module E-commerce

- **Gestion d'inventaire** : Suivi des produits invendus
- **Tarification compétitive** : Algorithmes pour optimiser les prix
- **Traitement des commandes** : Système complet de gestion des commandes

### 6. Interface Utilisateur

- **Dashboard responsive** : Interface moderne avec thème sombre et éléments vert néon
- **Visualisations de données** : Graphiques et tableaux pour le suivi des performances
- **Gestion des stratégies et modèles** : Interface pour créer et surveiller les stratégies

## Installation

### Prérequis

- Python 3.10+
- Docker (optionnel)
- Clé API SuperAGI (pour l'orchestration avancée)

### Installation Automatisée

#### Sous Linux

```bash
# Cloner le dépôt
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Rendre le script d'installation exécutable
chmod +x install.sh

# Lancer l'installation
./install.sh
```

#### Sous Windows

```bash
# Cloner le dépôt
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Lancer l'installation
install.bat
```

### Installation Manuelle avec pip

```bash
# Cloner le dépôt
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Installer les dépendances
pip install -e .
pip install -r requirements.txt

# Configurer les clés API
python installer.py --config-only
```

### Installation avec Docker

```bash
# Cloner le dépôt
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# Lancer avec Docker Compose
docker-compose up
```

## Utilisation

### Démarrer l'API

```bash
uvicorn autobot.main:app --host 0.0.0.0 --port 8000 --reload
```

### Accéder à l'interface

Ouvrez votre navigateur et accédez à `http://localhost:8000/dashboard`

### API Documentation

La documentation de l'API est disponible à `http://localhost:8000/docs`

### Configuration de SuperAGI

#### Via le script d'installation

```bash
python src/installer.py --superagi-key="VOTRE_CLE_API_SUPERAGI"
```

#### Configuration manuelle

1. Créez un fichier `config/superagi_config.yaml` avec votre clé API SuperAGI :

```yaml
api_key: "votre_clé_api_superagi"
base_url: "https://api.superagi.com"
enabled: true
```

2. Redémarrez AUTOBOT pour appliquer les changements.

### Utilisation de l'interface conversationnelle

Une fois SuperAGI configuré, vous pouvez interagir avec AUTOBOT via l'interface de chat :

1. Accédez à l'interface web d'AUTOBOT (http://localhost:8000/simple)
2. Cliquez sur l'onglet "Chat"
3. Entrez vos commandes en langage naturel

Exemples de commandes :

```
> @AutobotMaster Démarre 5 clones HFT, exécute backtest, et rapporte-moi le PnL.
> Prédis le prix de BTC pour demain
> Lance un backtest sur la stratégie momentum avec ETH/USD
> Entraîne le modèle avec les données des 30 derniers jours
```

### Configuration des clés API

#### Via l'interface FastAPI

Une fois l'application démarrée, accédez à l'endpoint `/setup` pour configurer vos clés API:

```bash
curl -X POST "http://localhost:8000/setup" -H "Content-Type: application/json" -d '{
  "binance": {
    "api_key": "votre_cle_binance",
    "api_secret": "votre_secret_binance"
  }
}'
```

#### Via le script de configuration

```bash
python installer.py --config-only
```

### Backtests et Trading Réel

#### Lancer les backtests

```bash
python run_backtests.py
```

#### Passer du backtest au trading réel

1. Assurez-vous que les backtests sont terminés et ont des résultats positifs
2. Vérifiez les métriques de performance dans le dossier `results/`
3. Activez le mode trading réel:

```bash
python -m src.autobot.main --live-trading
```

## Modules Principaux

### Trading

```python
from autobot.trading.strategy import MovingAverageStrategy
from autobot.providers.ccxt_provider_enhanced import CCXTProviderEnhanced

# Créer un fournisseur d'échange
provider = CCXTProviderEnhanced()
exchange = provider.create_exchange("binance", "api_key", "api_secret")

# Créer une stratégie
strategy = MovingAverageStrategy(
    name="ma_cross",
    exchange=exchange,
    symbol="BTC/USDT",
    timeframe="1h",
    parameters={"short_window": 10, "long_window": 50}
)

# Démarrer la stratégie
strategy.start()
```

### Apprentissage par Renforcement

```python
from autobot.rl.agent import RLAgent
from autobot.rl.env import TradingEnvironment
from autobot.rl.train import train_agent

# Créer un environnement
env = TradingEnvironment(
    exchange=exchange,
    symbol="BTC/USDT",
    timeframe="1h",
    parameters={"window_size": 100}
)

# Créer un agent
agent = RLAgent(
    name="dqn_agent",
    agent_type="dqn",
    env=env,
    parameters={"learning_rate": 0.001, "gamma": 0.99}
)

# Entraîner l'agent
train_agent(agent, episodes=1000)
```

### Orchestrateur Multi-Agent avec SuperAGI

```python
from autobot.agents.autobot_master import create_autobot_master_agent

# Créer l'agent AutobotMaster
master_agent = create_autobot_master_agent(
    api_key="votre_clé_api_superagi",
    base_url="https://api.superagi.com"
)

# Traiter une commande en langage naturel
response = master_agent.process_message(
    "Démarre 5 clones HFT sur BTC/USD et ETH/USD avec la stratégie momentum"
)

print(response)  # Affiche la réponse de l'agent

# Utilisation avec l'orchestrateur existant
from autobot.agents.orchestrator import AgentOrchestrator

# Créer un orchestrateur
orchestrator = AgentOrchestrator()

# Ajouter des agents
agent_id = orchestrator.add_agent(
    agent_type="trading",
    agent_config={
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "strategy": "ma_cross"
    }
)

# Démarrer l'orchestrateur
orchestrator.start()
```

### E-commerce

```python
from autobot.ecommerce.inventory_manager import InventoryManager

# Créer un gestionnaire d'inventaire
inventory_manager = InventoryManager()

# Synchroniser l'inventaire
inventory_manager.sync_inventory()

# Optimiser les prix
inventory_manager.optimize_prices()

# Passer une commande
order = inventory_manager.place_order(
    product_ids=["product1", "product2"],
    quantities=[1, 2],
    user_id="user123"
)
```

## Orchestration 100% UI

AUTOBOT propose désormais une orchestration 100% UI qui ne nécessite aucune interaction avec le terminal. Cette fonctionnalité permet :

- Une configuration initiale simplifiée via un formulaire unique
- Des backtests automatiques avec suivi en temps réel
- Un passage automatique en production basé sur des seuils configurables
- Des backtests continus pour affiner les stratégies en permanence
- Une gestion simplifiée du ghosting (duplication d'instances)

Pour plus de détails, consultez la section "Orchestration 100% UI" dans le [Guide de Connexion](GUIDE_CONNEXION.md).

## Licence

Ce projet est sous licence propriétaire. Tous droits réservés.

### Vérification de licence

Toutes les routes API et UI nécessitent une clé de licence valide. La clé est définie dans le fichier `.env` :

```
LICENSE_KEY=<votre_clé_de_licence>
```

### Guide de test API

Une fois le serveur démarré, vous pouvez tester l'API avec les commandes curl suivantes:

#### Vérifier l'état du serveur
```bash
curl http://localhost:8000/health
```

#### Obtenir un token d'authentification
```bash
curl -X POST -F "username=admin" -F "password=votre_mot_de_passe_fort" http://localhost:8000/token
```

#### Détecter du texte avec l'API mobile
```bash
curl -G "http://localhost:8000/api/mobile/detect?text=exemple" -H "Authorization: Bearer <jwt>" -H "X-License-Key: <votre_clé_de_licence>"
```

#### Lister les modèles de prédiction
```bash
curl http://localhost:8000/api/prediction/models -H "Authorization: Bearer <jwt>" -H "X-License-Key: <votre_clé_de_licence>"
```

#### Entraîner un modèle de prédiction de texte
```bash
curl -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <jwt>" -H "X-License-Key: <votre_clé_de_licence>" -d '{"data":[{"text":"Exemple de texte positif","label":1},{"text":"Exemple de texte négatif","label":0}]}' http://localhost:8000/api/prediction/train?model_name=text_model&model_type=TextClassificationModel
```

#### Faire une prédiction avec un modèle de texte
```bash
curl -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <jwt>" -H "X-License-Key: <votre_clé_de_licence>" -d '{"data":[{"text":"Nouveau texte à prédire"}]}' http://localhost:8000/api/prediction/predict?model_name=text_model
```

#### Accéder au dashboard complet avec authentification
```bash
curl -H "Authorization: Bearer <jwt>" -H "X-License-Key: <votre_clé_de_licence>" -H "Accept: text/html" http://localhost:8000/dashboard/
```

## Auteur

Développé par Flobi30 avec l'assistance de Devin AI.
