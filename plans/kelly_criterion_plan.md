# /dh:add-new-feature — Kelly Criterion Sizing pour AutoBot V2

## Feature Summary
Implémenter le module **Kelly Criterion Sizing** qui calcule la taille de position optimale 
basée sur le Profit Factor historique de chaque instance de trading.

## Motivation
Actuellement, AutoBot utilise un sizing statique (risk_per_trade fixe dans RiskManager).
Le Kelly Criterion permet d'optimiser dynamiquement la taille de position en fonction 
de la performance historique réelle de chaque instance, maximisant la croissance du capital 
tout en limitant le risque de ruine.

## Technical Design

### Formule
```
f* = (p × b - q) / b

où :
  p = win_rate (proportion de trades gagnants)
  q = 1 - p (proportion de trades perdants)
  b = avg_win / avg_loss (ratio gain moyen / perte moyenne)
```

### Garde-fous
1. **Half-Kelly** : On utilise f*/2 pour réduire la variance (standard en finance quantitative)
2. **Cap à 25%** : Jamais plus de 25% du capital sur une seule position (`max_position_pct`)
3. **Plancher à 0** : Si Kelly est négatif (edge négatif), taille = 0 (ne pas trader)
4. **PF Filter** : Si Profit Factor < 1.0, désactiver le sizing (pas d'edge)

### Cas limites gérés
| Cas | Comportement |
|-----|-------------|
| `avg_loss == 0` | Retourne 0.0 (division par zéro impossible) |
| `avg_win == 0` | Retourne 0.0 (pas de gain → pas de sizing) |
| `win_rate <= 0 ou >= 1` | Retourne 0.0 (données invalides) |
| `current_capital <= 0` | Retourne 0.0 |
| `current_pf < 1.0` | Retourne 0.0 (pas d'edge statistique) |
| `kelly_fraction < 0` | Retourne 0.0 (edge négatif, ne pas trader) |

### Thread Safety
- `threading.RLock` sur toutes les méthodes publiques (cohérent avec ATRFilter et conventions CONTEXT.md)

### Interface publique
```python
class KellyCriterion:
    __init__(max_position_pct: float = 0.25)
    calculate_position_size(win_rate, avg_win, avg_loss, current_capital, current_pf) -> float
    get_kelly_fraction(win_rate, avg_win, avg_loss) -> float  # Kelly brut (debug/dashboard)
    get_status() -> dict  # Pour dashboard API
    reset() -> None
```

## Files to Create
- `src/autobot/v2/modules/kelly_criterion.py` — Module principal
- `src/autobot/v2/tests/test_kelly_criterion.py` — Tests unitaires

## Files to Modify
- `CONTEXT.md` — Mettre à jour le statut du module Kelly Criterion

## Implementation Steps

### Step 1: Create kelly_criterion.py
- Classe `KellyCriterion` avec toutes les méthodes
- Docstrings complètes, style cohérent avec atr_filter.py
- Logging en langage humain
- RLock thread-safety
- Gestion exhaustive des cas limites

### Step 2: Create test_kelly_criterion.py
- Tests des cas nominaux (Kelly positif, Half-Kelly, cap 25%)
- Tests des cas limites (division par zéro, valeurs négatives, PF < 1)
- Tests thread-safety (concurrent access)
- Tests du statut et reset

### Step 3: Update CONTEXT.md
- Marquer Kelly Criterion comme ✅ Implémenté dans la liste des modules

## Acceptance Criteria
- [ ] `calculate_position_size()` retourne Half-Kelly cappé à 25%
- [ ] Tous les cas limites retournent 0.0 sans exception
- [ ] Thread-safe via RLock
- [ ] Aucune dépendance externe
- [ ] Calcul O(1)
- [ ] Logs en langage humain
- [ ] Tests passent à 100%
