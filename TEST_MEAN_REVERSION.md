## MISSION: Test Mean Reversion — Validation Pas de Double-Push

### Contexte
Bug trouvé: `should_enter()` et `should_exit()` font toutes les deux `self._push(price)`.
Si appelé séquentiellement, le même prix est pushé 2 fois → stats corrompues.

### Fichier à tester
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/mean_reversion.py

### Tests à créer
dans src/autobot/v2/tests/test_mean_reversion_double_push.py:

1. **test_update_once_per_tick**
   - Appeler update(price) une fois
   - Vérifier que la fenêtre a bien 1 élément
   
2. **test_should_enter_no_push**
   - Appeler update(price) → should_enter()
   - Vérifier que la fenêtre n'a pas doublé
   
3. **test_should_exit_no_push**
   - Appeler update(price) → should_exit()
   - Vérifier que la fenêtre n'a pas doublé
   
4. **test_no_double_push_sequential**
   - if strategy.should_enter(price): ... elif strategy.should_exit(price): ...
   - Vérifier que le prix n'est pushé qu'une seule fois
   
5. **test_window_size_consistency**
   - Pousser 100 prix
   - Vérifier que window_size = 100 (pas 200)

### Livrables
1. Fichier test complet
2. Tests passant à 100%
