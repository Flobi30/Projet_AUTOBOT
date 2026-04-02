## MISSION: Corrections Critiques Sécurité P0-P6 — PHASE 1 (Urgent)

### Contexte
Review Opus a trouvé 6 failles CRITIQUES + W9 catastrophique. Cette mission corrige la Phase 1 (urgent).

### Fichiers à corriger

**C1 — Division par zéro hot path:**
- src/autobot/v2/instance_async.py (on_price_update)
- src/autobot/v2/strategies/grid_async.py
- src/autobot/v2/strategies/trend_async.py

**C5 — Validation données WebSocket:**
- src/autobot/v2/websocket_async.py (validate price > 0, finite, bid < ask)
- src/autobot/v2/instance_async.py (guard price)

**W9 — Fallback PRICE comme VOLUME (CATASTROPHIQUE):**
- src/autobot/v2/fast_order_builder.py (fix submit_speculative fallback)

### Corrections à appliquer

**C1 + C5 — Validation prix:**
```python
import math
def _validate_price(self, price: float) -> bool:
    if not math.isfinite(price) or price <= 0:
        logger.warning(f"❌ Prix invalide reçu: {price}")
        return False
    # Sanity check: variation < 10% par tick
    if hasattr(self, '_last_price') and self._last_price > 0:
        if abs(price - self._last_price) / self._last_price > 0.10:
            logger.warning(f"⚠️ Variation anormale: {self._last_price} → {price}")
            return False
    self._last_price = price
    return True
```

**W9 — Fix fallback:**
```python
# AVANT (BUG):
volume = template.fixed_price  # ❌ Prix au lieu du volume!
# APRÈS (FIX):
volume = int(capital // price)  # ✅ Volume calculé correctement
```

### Tests
Créer tests dans:
- src/autobot/v2/tests/test_price_validation.py
- src/autobot/v2/tests/test_fast_order_builder.py (test W9)

### Livrables
1. Code corrigé avec guards
2. Tests passant
3. Log des corrections
