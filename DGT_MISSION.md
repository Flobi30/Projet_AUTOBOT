## MISSION: Implémenter Recentrage Dynamique Grille (DGT) pour AutoBot V2

### Contexte
Basé sur le papier académique DGT (NTU, 2025). Amélioration du Profit Factor (+0.2 à +0.4).

### Objectif
Quand le prix sort de la grille, au lieu de terminer avec perte, recentrer la grille sur le prix actuel.

### Spécifications

1. **GridRecenteringManager**
   - Détecte quand prix dévie >7% du centre
   - Calcule nouveau centre = prix actuel
   - Recrée les niveaux de grille
   - Conserve le capital restant

2. **Conditions de recentrage**
   - Dérive > seuil (configurable, défaut 7%)
   - PAS en mode tendance forte (ADX < 25)
   - Cooldown entre recentrages (min 1h)
   - Max 3 recentrages par jour

3. **Risques mitigés**
   - Couplé avec RegimeDetector (pause si tendance)
   - Trail le centre si prix monte >5% (trailing anchor)
   - Logique de "grille glissante" douce

### Fichiers à créer
1. src/autobot/v2/grid_recentering.py — Manager DGT
2. src/autobot/v2/tests/test_grid_recentering.py — Tests

### Fichiers à modifier
- src/autobot/v2/strategies/grid_async.py — Intégrer DGT

### Contraintes
- Ne pas recentrer en tendance forte (évite cascade de pertes)
- Préserver le capital alloué
- Thread-safe (asyncio.Lock)
- Tests: recentrage normal, cooldown, blocage tendance

### Livrables
1. Code DGT avec docstrings
2. Tests passant
3. Résumé cas d'usage
