# AUTOBOT Grid Trading Bot

Bot de trading algorithmique utilisant la stratégie Grid sur Kraken.

## 🚀 Démarrage Rapide

### Prérequis
- Python 3.11+
- Compte Kraken avec API keys
- Docker (optionnel)

### Installation

```bash
# 1. Cloner le repo
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer
cp .env.example .env
# Éditez .env avec vos clés API

# 4. Lancer en mode simulation (sandbox)
python -m autobot.main
```

## ⚙️ Configuration

Copiez `.env.example` en `.env` et modifiez :

```bash
# Mode sandbox (recommandé pour test)
AUTOBOT_SANDBOX=true

# Pour production (ORDRES RÉELS)
AUTOBOT_SANDBOX=false
AUTOBOT_PRODUCTION_CONFIRMED=YES_I_KNOW_WHAT_IM_DOING
KRAKEN_API_KEY=votre_cle
KRAKEN_API_SECRET=votre_secret
```

### Paramètres de Trading

| Variable | Défaut | Description |
|----------|--------|-------------|
| `AUTOBOT_SYMBOL` | XXBTZEUR | Paire de trading |
| `AUTOBOT_CAPITAL` | 500.0 | Capital total (€) |
| `AUTOBOT_NUM_LEVELS` | 14 | Nombre de niveaux (pair) |
| `AUTOBOT_RANGE_PERCENT` | 14.0 | Range totale (+/- 7%) |

### Sécurité

| Variable | Défaut | Description |
|----------|--------|-------------|
| `AUTOBOT_MAX_ORDER_VALUE` | 100.0 | Max par ordre (€) |
| `AUTOBOT_MAX_VOLUME` | 0.01 | Max par ordre (BTC) |
| `AUTOBOT_MAX_POSITIONS` | 10 | Max positions ouvertes |
| `AUTOBOT_MAX_DRAWDOWN` | 20.0 | Stop-loss global (%) |

## 🐳 Docker

```bash
# Construire et lancer
docker-compose -f docker-compose.prod.yml up -d

# Voir les logs
docker logs -f autobot-trading

# Arrêter
docker-compose -f docker-compose.prod.yml down
```

## 📊 Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  main.py    │────▶│ TradingBot   │────▶│ GridCalc    │
└─────────────┘     └──────────────┘     └─────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ OrderManager │    │ PositionMgr  │    │ MarketData   │
└──────────────┘    └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
                    ┌──────────────┐
                    │    Kraken    │
                    │     API      │
                    └──────────────┘
```

## 🧪 Tests

```bash
pytest tests/ -v
```

## ⚠️ Avertissements

- **NE JAMAIS** commiter vos clés API
- **TOUJOURS** tester en sandbox avant production
- Le trading comporte des risques de perte en capital

## 📄 Licence

MIT
