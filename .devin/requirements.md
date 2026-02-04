# Grid Trading Engine v1.0 - Phase 2 AUTOBOT

## Objectif
Développer un Grid Trading Engine complet pour AUTOBOT avec les spécifications suivantes.

## Configuration Grid
- Grid STATIQUE (pas trailing)
- 15 niveaux équidistants
- Range: +/-7% autour du prix central
- Capital: 500€
- Allocation par niveau: ~33€
- Profit par niveau: 0.8%
- Objectif mensuel: +15%

## Modules à implémenter

### 1. Grid Calculator (`/src/grid_engine/grid_calculator.py`)
- Calcul des 15 niveaux équidistants
- Range +/-7% autour du prix central
- Espacement uniforme entre niveaux

### 2. Order Manager (`/src/grid_engine/order_manager.py`)
- Placement ordres achat/vente sur chaque niveau
- Réinvestissement automatique des gains
- Gestion du cycle buy low / sell high

### 3. Position Tracker (`/src/grid_engine/position_tracker.py`)
- Suivi P&L temps réel
- Historique des trades
- Métriques de performance

### 4. Rebalance (`/src/grid_engine/rebalance.py`)
- Détection sortie du grid
- Rééquilibrage automatique si prix sort du range
- Recalcul des niveaux

### 5. Risk Manager (`/src/grid_engine/risk_manager.py`)
- Stop global: -20% du capital
- Daily loss limit: -50€
- Emergency stop (fermeture totale)

## Configuration
- `config/grid_btc_500.yml`: Instance BTC/USDT, 500€, 15 niveaux
- Template pour futures instances (ETH, Forex)

## Intégration
- Connexion au data_connector existant (IB)
- API endpoints pour dashboard React
- WebSocket temps réel prix/positions

## Contraintes Techniques
- Binance spot uniquement (pas futures)
- Latence cible: <200ms
- Tests unitaires: >90% coverage

## Validation
- Attendre GO Kimi/Flo avant merge
- Papier trading Binance 1 semaine
- Scénarios: range, breakout, flash crash

## Priorité
ROBUSTESSE > Performance
