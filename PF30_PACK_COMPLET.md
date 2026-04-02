## MISSION: Implémenter Toutes les Stratégies PF 3.0+ — Pack Complet

### Contexte
Objectif: Passer de PF 1.5 à 3.0+ avec toutes les optimisations identifiées.

---

## 🔴 PRIORITÉ 1 — Quick Wins (Fort Impact, Simple)

### 1. Trailing Stop ATR
**Fichier:** src/autobot/v2/modules/trailing_stop_atr.py
**Description:** Stop-loss dynamique basé sur ATR avec trailing

```python
class TrailingStopATR:
    def __init__(self, atr_multiplier=2.5, activation_profit=1.5):
        self.atr_multiplier = atr_multiplier  # Distance SL
        self.activation_profit = activation_profit  # Activation trailing (× ATR)
    
    def update(self, price: float, atr: float, entry_price: float) -> Optional[float]:
        # SL initial = entry - (2.5 × ATR)
        # Activer trailing quand profit > (1.5 × ATR)
        # Trail = price - (2.5 × ATR), jamais descendre
        pass
```

### 2. Kelly Criterion Dynamique
**Fichier:** src/autobot/v2/modules/kelly_criterion.py (modifier)
**Description:** Kelly qui scale down après pertes consécutives

```python
def calculate_position_size_dynamic(self, win_rate, avg_win, avg_loss, 
                                   capital, current_pf, consecutive_losses=0):
    kelly = self._calculate_kelly_fraction(win_rate, avg_win, avg_loss)
    # Décrément après 3 pertes: f = base × 0.85^n
    if consecutive_losses >= 3:
        kelly *= (0.85 ** (consecutive_losses - 2))
    return min(kelly * 0.5 * capital, capital * 0.02)  # Half-Kelly, max 2%
```

---

## 🟡 PRIORITÉ 2 — Avancé (Moyen Impact)

### 3. Multi-Strategy Ensemble
**Fichier:** src/autobot/v2/strategy_ensemble.py
**Description:** Combine Grid + Trend + Mean Reversion avec poids dynamiques

```python
class StrategyEnsemble:
    STRATEGIES = {
        'grid': GridStrategy,
        'trend': TrendStrategy, 
        'mean_reversion': MeanReversionStrategy
    }
    
    def get_signal(self, price, regime):
        # Poids selon régime:
        # RANGE: Grid 70%, MeanRev 30%, Trend 0%
        # TREND_FAIBLE: Grid 40%, Trend 40%, MeanRev 20%
        # TREND_FORTE: Trend 80%, Grid 20%, MeanRev 0%
        pass
```

### 4. Pyramiding Contrôlé
**Fichier:** src/autobot/v2/modules/pyramiding_manager.py
**Description:** Ajouter à une position gagnante avec trailing serré

```python
class PyramidingManager:
    MAX_ADDS = 3
    SCALE_INCREMENTS = [1.0, 1.3, 1.5]  # Multiplicateurs position
    
    def should_add_position(self, current_profit_pct, level):
        # Ajouter si profit > 2%, trailing stop serré sur ajouts
        pass
```

### 5. Inverse Volatility Weighting
**Fichier:** src/autobot/v2/modules/volatility_weighter.py
**Description:** Allouer plus de capital aux paires moins volatiles

```python
def calculate_weights(instances, atr_values):
    # Weight_i = (1/ATR_i) / Σ(1/ATR_j)
    # Moins volatil = plus de poids
    pass
```

---

## 🟢 PRIORITÉ 3 — Validation & Tests

### Tests à créer
1. test_trailing_stop_atr.py — Tests trailing activation, jamais baisse
2. test_kelly_dynamic.py — Tests décrément après pertes
3. test_strategy_ensemble.py — Tests pondération régime
4. test_pyramiding.py — Tests ajouts progressifs
5. test_volatility_weighter.py — Tests poids inverse ATR

---

## Fichiers à modifier
- src/autobot/v2/instance_async.py — Intégrer trailing stop
- src/autobot/v2/orchestrator_async.py — Intégrer ensemble
- src/autobot/v2/strategies/grid_async.py — Pyramiding

---

## Livrables
1. 5 modules nouveaux
2. 5 fichiers de tests (tous passent)
3. Documentation intégration
