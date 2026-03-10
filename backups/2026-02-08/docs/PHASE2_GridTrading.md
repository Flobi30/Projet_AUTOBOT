# 🎯 PHASE 2 - Grid Trading Implementation

## Status: READY TO START (Attente merge PR #39)

---

## 📋 Objectifs Phase 2

### Grid Trading Statique v1.0
- **Capital:** 500€
- **Marché:** BTC/USDT (Binance)
- **Strategy:** Grid 15 niveaux, TP/SL fixes
- **Objectif:** +15% mensuel (75€)
- **Risk:** Stop global -20%

---

## 🏗️ Architecture Grid

```
┌─────────────────────────────────────────┐
│         GRID TRADING ENGINE             │
│                                         │
│  Prix actuel: 100,000$                  │
│                                         │
│  Sell 107,000$ ←──── Niveau 15          │
│  Sell 106,000$ ←──── Niveau 14          │
│  Sell 105,000$ ←──── Niveau 13          │
│       ...                               │
│  Sell 101,000$ ←──── Niveau 1           │
│                                         │
│  ───────── PRIX ACTUEL ─────────        │
│                                         │
│  Buy  99,000$  ←──── Niveau 1  [ACTIF]  │
│  Buy  98,000$  ←──── Niveau 2  [ACTIF]  │
│  Buy  97,000$  ←──── Niveau 3  [ACTIF]  │
│       ...                               │
│  Buy  93,000$  ←──── Niveau 15 [ACTIF]  │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🔧 Spécifications Techniques

### Grid Calculator
```python
class GridCalculator:
    def __init__(self, capital: float, levels: int, 
                 current_price: float, range_percent: float):
        self.capital = capital
        self.levels = levels
        self.current_price = current_price
        self.range_percent = range_percent
    
    def calculate_grid(self) -> List[GridLevel]:
        """
        Calcule niveaux équidistants
        Range: +/- 7% du prix actuel
        """
        pass
```

### Order Manager
- Place ordres d'achat (below price)
- Place ordres de vente (above price + profit)
- Réinvestit automatiquement les gains
- Stop global si drawdown > 20%

### Configuration (config/grid_btc_500.yml)
```yaml
instance:
  name: "AUTOBOT-BTC-500"
  version: "1.0.0"

capital:
  total: 500.0
  per_level: 33.33

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
  max_drawdown: 20.0
  daily_loss: 50.0
  emergency_stop: true
```

---

## 📅 Planning Phase 2

| Jour | Tâche | Agent | Livrable |
|------|-------|-------|----------|
| J1 | Grid Calculator + Order Manager | Devin | Core engine |
| J2 | Integration Data Connector + Tests | Devin | Tests >90% |
| J3 | Review + Corrections | Claude | Code validé |
| J4 | Papier trading | Kimi | Validation 24h |
| J5 | Déploiement Hetzner + Live | Devin | Production 500€ |

---

## ✅ Checklist Départ Phase 2

- [ ] PR #39 mergée
- [ ] Data Connector IB stable
- [ ] Config Grid créée
- [ ] Tests unitaires planifiés
- [ ] Papier trading ready

---

## 🎯 Prochaines Étapes après Grid

1. **Semaine 2:** Papier trading + validation
2. **Semaine 3:** Live 500€ + monitoring
3. **Semaine 4:** Si +15% → Instance #2 (ETH, 1500€)

---

**Prêt à lancer dès que tu merges !** 🚀