## MISSION: Corrections Complètes — Stratégies + P0-P6

### Contexte
Fusion des problèmes trouvés dans:
- Review Stratégies (Opus + Kimi)  
- Review P0-P6 (Opus + Kimi)

---

## 🔴 PRIORITÉ 1 — CRITIQUES (Bloquants Production)

### S1 — Validation Prix (NaN/Inf) — TOUTES les stratégies
**Fichiers:**
- src/autobot/v2/strategies/grid_async.py
- src/autobot/v2/strategies/grid.py  
- src/autobot/v2/strategies/trend_async.py
- src/autobot/v2/strategies/trend.py
- src/autobot/v2/instance_async.py

**Correction:**
```python
import math

def _validate_price(self, price: float) -> bool:
    if not math.isfinite(price) or price <= 0:
        logger.warning(f"❌ Prix invalide: {price}")
        return False
    # Sanity check variation < 10%
    if hasattr(self, '_last_price') and self._last_price > 0:
        if abs(price - self._last_price) / self._last_price > 0.10:
            logger.warning(f"⚠️ Variation anormale: {self._last_price} → {price}")
            return False
    self._last_price = price
    return True
```

### S2 — Double-Push Mean Reversion (CORROMPT STATS)
**Fichier:** src/autobot/v2/strategies/mean_reversion.py

**Problème:** `should_enter()` et `should_exit()` font toutes les deux `self._push(price)`

**Correction:** Séparer update et décision
```python
def update(self, price: float) -> None:
    """Push prix UNE SEULE FOIS par tick"""
    with self._lock:
        self._push(price)

def should_enter(self) -> bool:
    """Décision sans push"""
    with self._lock:
        # PAS de _push ici
        return self._price < self._lower_band
```

### S3 — Emergency Price Jamais Recalculé (GRID DRIFT)
**Fichiers:** src/autobot/v2/strategies/grid_async.py, grid.py

**Problème:** `_emergency_close_price` calculé une fois à l'init, jamais mis à jour

**Correction:** Dynamic recentering avec trailing
```python
def _check_grid_drift(self, price: float) -> bool:
    """Recalcule center_price si dérive > 5%"""
    if abs(price - self.center_price) / self.center_price > 0.05:
        self.center_price = price  # Recenter
        self._recalculate_grid_levels()
        self._emergency_close_price = self.center_price * (1 - self.range_percent * self._grid_invalidation_factor / 100)
        logger.info(f"🔄 Grille recentrée sur {price}")
        return True
    return False
```

### S4 — Division par Zéro Hot Path (INSTANCE)
**Fichier:** src/autobot/v2/instance_async.py

**Correction:** Guard avant division
```python
if price <= 0 or not math.isfinite(price):
    logger.error(f"❌ Prix invalide reçu: {price}")
    return
```

### S5 — Fallback PRICE comme VOLUME (CATASTROPHIQUE)
**Fichier:** src/autobot/v2/fast_order_builder.py

**Correction:** Volume calculé correctement
```python
# BUG: volume = template.fixed_price
# FIX:
volume = int(capital // price)
```

---

## 🟡 PRIORITÉ 2 — WARNINGS Importants

### W1 — Locks Imbriqués 7× dans Grid
**Fichier:** src/autobot/v2/strategies/grid.py

**Correction:** Une seule acquisition du lock au sommet de `on_price()`

### W2 — Stratégies Dormantes Sans Flag PRODUCTION_READY
**Fichiers:** mean_reversion.py, arbitrage.py, trend.py

**Correction:**
```python
class MeanReversionStrategy:
    PRODUCTION_READY = False  # Flag explicite
    
    def __init__(self, ...):
        if not self.PRODUCTION_READY:
            raise RuntimeError("❌ Stratégie non approuvée pour production")
```

### W3 — time.time() Non-Monotone (Arbitrage)
**Fichier:** src/autobot/v2/strategies/arbitrage.py

**Correction:** Remplacer par `time.monotonic()`

### W4 — datetime.now() dans Hot Path
**Fichiers:** Toutes les stratégies

**Correction:** Remplacer par `time.time()` (appel C rapide)

### W5 — Stop-Loss Client-Side Uniquement
**Fichiers:** Toutes les stratégies

**Correction:** Placer ordres stop-limit sur exchange (pas juste client-side)

### W6 — Aucune Validation des Montants
**Fichiers:** Toutes les stratégies

**Correction:** Vérifier volume minimum exchange (Kraken: 0.0001 BTC)

---

## 🟢 PRIORITÉ 3 — Améliorations

### I1 — Duplication Code grid.py / grid_async.py
**Action:** Factoriser la logique commune dans une classe de base

### I2 — Validation WebSocket Données
**Fichier:** src/autobot/v2/websocket_async.py

**Correction:** Vérifier bid < ask, price > 0, spread raisonnable

---

## Tests à Créer

1. test_price_validation.py — NaN, Inf, variation anormale
2. test_mean_reversion.py — Pas de double-push
3. test_grid_drift.py — Recentering dynamique
4. test_production_flag.py — Stratégies dormantes
5. test_volume_validation.py — Montants minimums

---

## Livrables
1. Toutes les corrections P1 (S1-S5)
2. Tests passant
3. Log des changements
