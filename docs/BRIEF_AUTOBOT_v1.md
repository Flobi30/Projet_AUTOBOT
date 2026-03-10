# BRIEF DEVELOPPEMENT - AUTOBOT v1.0

## Date: 2026-02-04
## Architecte: Kimi
## Developpeur: Devin
## Status: APPROVED - Ready for implementation

---

## 🎯 OBJECTIF
Developper AUTOBOT v1.0 - Grid Trading Statique
- Capital depart: 500€
- Strategy: Grid simple (TP/SL fixes)
- Objectif performance: +15% mensuel
- Architecture: Multi-instance scalable

---

## 📦 STRUCTURE DU PROJET

```
Projet_AUTOBOT/
├── src/
│   ├── grid_engine/           # NOUVEAU
│   │   ├── __init__.py
│   │   ├── calculator.py      # Calcul niveaux grid
│   │   ├── executor.py        # Execution ordres
│   │   ├── monitor.py         # Monitoring positions
│   │   └── risk_manager.py    # Stop loss global
│   │
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── binance_client.py  # API Binance
│   │   └── base_connector.py  # Classe abstraite
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── position.py        # Model Position
│   │   ├── grid_level.py      # Model Niveau Grid
│   │   └── trade.py           # Model Trade
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py          # Chargement YAML
│   │   └── validator.py       # Validation config
│   │
│   └── dashboard/             # INTEGRER EXISTANT
│       └── api.py             # API pour frontend
│
├── config/
│   ├── template.yml           # Template configuration
│   ├── instance_1_btc.yml     # Instance 1: BTC/USD 500€
│   └── README.md              # Guide configuration
│
├── tests/
│   ├── test_grid_engine/
│   ├── test_connectors/
│   └── test_integration/
│
├── frontend/                  # A RECUPERER
│   └── [Contenu de "Nouveau Frontend AUTOBOT.zip"]
│
└── docker/
    ├── Dockerfile.instance    # Image par instance
    └── docker-compose.yml     # Multi-instances
```

---

## 🔧 SPECIFICATIONS TECHNIQUES

### 1. Grid Engine (STATIQUE - PAS DYNAMIQUE)

#### Grid Calculator
```python
class GridCalculator:
    def __init__(self, config: GridConfig):
        self.capital = config.capital
        self.levels = config.levels
        self.range_percent = config.range_percent
        self.current_price = config.current_price
    
    def calculate_levels(self) -> List[GridLevel]:
        """
        Calcule niveaux grid fixes
        Retourne: Liste de niveaux (prix_achat, prix_vente, amount)
        """
        pass
    
    def calculate_position_size(self) -> Decimal:
        """
        Capital / Niveaux = Taille position
        Ex: 500€ / 15 niveaux = 33.33€ par niveau
        """
        pass
```

#### Order Executor
```python
class OrderExecutor:
    def __init__(self, connector: ExchangeConnector):
        self.connector = connector
    
    async def place_grid_orders(self, levels: List[GridLevel]):
        """
        Place tous les ordres d'achat et vente
        Un ordre par niveau
        """
        pass
    
    async def handle_fill(self, order: Order):
        """
        Quand un ordre est executé:
        - Log le trade
        - Placer ordre inverse (grid statique)
        - Mettre a jour P&L
        """
        pass
```

### 2. Configuration YAML

#### Template (config/template.yml)
```yaml
instance:
  name: "AUTOBOT-Instance-X"
  version: "1.0.0"
  
capital:
  total: 500.0                    # Capital total en EUR
  max_per_level: 33.33           # Capital / niveaux
  reserve: 0.0                    # Reserve (0 = tout en grid)

market:
  exchange: "binance"            # ou "interactive_brokers"
  symbol: "BTC/USDT"             # Pair trading
  type: "spot"                   # spot, futures, forex
  
grid:
  type: "static"                 # STATIQUE - pas de trailing
  levels: 15                     # Nombre niveaux
  range_percent: 7.0             # Range grid (+/- 7%)
  profit_per_level: 0.8          # Profit cible par niveau (%)
  
  # Exemple BTC a 100,000:
  # Niveau 1: Buy 93,000 / Sell 100,000
  # Niveau 2: Buy 86,000 / Sell 93,000
  # ...
  # Niveau 15: Buy 7,000 / Sell 14,000 (exemple)

risk:
  max_drawdown_percent: 20.0     # Stop si -20%
  daily_loss_limit: 50.0         # Stop si -50€ dans journee
  max_open_positions: 15         # Max positions ouvertes
  
logging:
  level: "INFO"
  file: "logs/autobot.log"
  format: "json"                 # JSON pour parsing facile
```

#### Instance 1 (config/instance_1_btc.yml)
```yaml
instance:
  name: "AUTOBOT-BTC-500"
  
capital:
  total: 500.0
  max_per_level: 33.33

market:
  exchange: "binance"
  symbol: "BTC/USDT"
  type: "spot"
  
grid:
  type: "static"
  levels: 15
  range_percent: 7.0
  profit_per_level: 0.8

risk:
  max_drawdown_percent: 20.0
  daily_loss_limit: 50.0
```

### 3. Risk Manager (CRITIQUE)

```python
class RiskManager:
    def __init__(self, config: RiskConfig):
        self.max_drawdown = config.max_drawdown_percent
        self.daily_loss_limit = config.daily_loss_limit
        self.initial_capital = config.capital
        self.current_pnl = 0.0
    
    def check_risk(self) -> RiskStatus:
        """
        Verifie:
        1. Drawdown actuel < max_drawdown
        2. Perte journaliere < daily_loss_limit
        3. Connexion exchange OK
        
        Returns: OK, WARNING, CRITICAL, STOP
        """
        pass
    
    def emergency_stop(self, reason: str):
        """
        STOP IMMEDIAT:
        - Annuler tous les ordres ouverts
        - Fermer toutes les positions
        - Logger l'evenement
        - Notifier dashboard
        """
        pass
```

### 4. Multi-Instance Architecture

#### Docker Compose
```yaml
version: '3.8'

services:
  # Instance 1: BTC Grid 500€
  autobot-btc:
    build:
      context: .
      dockerfile: docker/Dockerfile.instance
    container_name: autobot-btc
    volumes:
      - ./config/instance_1_btc.yml:/app/config.yml
      - ./data/btc:/app/data
    environment:
      - INSTANCE_NAME=AUTOBOT-BTC-500
      - API_KEY_BINANCE=${BINANCE_API_KEY}
      - API_SECRET_BINANCE=${BINANCE_SECRET}
    restart: unless-stopped
    
  # Instance 2: ETH Grid (active quand Flo ajoute capital)
  autobot-eth:
    build:
      context: .
      dockerfile: docker/Dockerfile.instance
    container_name: autobot-eth
    volumes:
      - ./config/instance_2_eth.yml:/app/config.yml
      - ./data/eth:/app/data
    environment:
      - INSTANCE_NAME=AUTOBOT-ETH-1500
      - API_KEY_BINANCE=${BINANCE_API_KEY}
    restart: unless-stopped
    profiles: ["eth"]  # Demarre manuellement
    
  # Dashboard (React existant)
  dashboard:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - API_URL=http://autobot-btc:8080
    depends_on:
      - autobot-btc
```

#### Duplication Instance (Guide pour Flo)
```bash
# 1. Copier config template
cp config/template.yml config/instance_2_eth.yml

# 2. Modifier instance_2_eth.yml:
#    - name: "AUTOBOT-ETH-1500"
#    - capital: 1500
#    - symbol: "ETH/USDT"
#    - levels: 12

# 3. Ajouter dans docker-compose.yml (copier service autobot-btc)

# 4. Demarrer
docker-compose --profile eth up -d autobot-eth
```

### 5. Dashboard API Integration

```python
# src/dashboard/api.py
from fastapi import FastAPI
from typing import List

app = FastAPI()

@app.get("/api/instances")
def get_instances() -> List[InstanceStatus]:
    """Liste toutes les instances actives"""
    pass

@app.get("/api/instance/{id}/status")
def get_instance_status(id: str) -> InstanceStatus:
    """Status d'une instance (capital, P&L, positions)"""
    pass

@app.get("/api/instance/{id}/pnl")
def get_instance_pnl(id: str, period: str) -> PnLReport:
    """P&L historique"""
    pass

@app.post("/api/instance/{id}/stop")
def stop_instance(id: str):
    """Arreter une instance"""
    pass

@app.post("/api/instance/create")
def create_instance(config: InstanceConfig):
    """Creer nouvelle instance (pour duplication)"""
    pass
```

---

## 🧪 TESTS REQUIS

### Tests Unitaires (>90% coverage)
```python
# tests/test_grid_calculator.py
def test_calculate_levels():
    config = GridConfig(capital=500, levels=15, range_percent=7)
    calc = GridCalculator(config)
    levels = calc.calculate_levels()
    assert len(levels) == 15
    assert sum([l.amount for l in levels]) <= 500

def test_position_size():
    assert calculate_position_size(500, 15) == Decimal("33.33")
```

### Tests Integration
- Connexion Binance testnet
- Placement ordres grid
- Execution et rebouclage
- Stop loss declenchement

### Tests Charge (Papier)
- 24h de trading continu
- 100+ trades executes
- Latence moyenne < 200ms

---

## 📋 CHECKLIST LIVRAISON

### Avant review (Devin)
- [ ] Grid calculator implemente
- [ ] Order executor fonctionne
- [ ] Risk manager operationnel
- [ ] Config YAML chargeable
- [ ] Tests >90%
- [ ] Documentation complete

### Review (Claude)
- [ ] Code propre (PEP8)
- [ ] Pas de secrets durs
- [ ] Gestion erreurs complete
- [ ] Logs adequats
- [ ] Securite OK

### Validation (Kimi)
- [ ] Architecture respectee
- [ ] Config modulaire
- [ ] Multi-instance ready
- [ ] Frontend integrable

### Decision (Flo)
- [ ] GO pour test papier
- [ ] ou Modifications demandees

---

## 🚨 CONTRAINTES STRICTES

1. **GRID STATIQUE UNIQUEMENT**
   - Pas de trailing stop
   - Pas de deplacement TP/SL
   - Pas de prediction tendance
   - Niveaux fixes au demarrage

2. **RISK MANAGEMENT OBLIGATOIRE**
   - Stop global -20%
   - Max 2% par niveau
   - Daily loss limit
   - Emergency stop fonctionnel

3. **PAS DE COMPLEXITE INUTILE**
   - Pas de ML
   - Pas d'indicateurs techniques
   - Pas de sentiment analysis
   - KISS: Keep It Simple, Stupid

4. **TESTS OBLIGATOIRES**
   - Unitaire >90%
   - Integration papier trading
   - 1 semaine stable avant merge

---

## 🎯 PROCHAINES ETAPES

1. **Semaine 1:** Implementation + tests locaux
2. **Semaine 2:** Papier trading + corrections
3. **Semaine 3:** Review + validation + merge
4. **Semaine 4:** Deploiement Hetzner + live

---

## 📞 CONTACT

- **Architecte:** Kimi (OpenClaw)
- **Developpeur:** Devin (Cognition)
- **Reviewer:** Claude (Anthropic)
- **Decisionnaire:** Flo (Proprietaire)

**Status:** READY TO CODE