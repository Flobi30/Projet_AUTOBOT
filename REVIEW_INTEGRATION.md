## MISSION: Review Intégration Complète — AutoBot V2 Production Ready

Tu es expert en intégration système. Vérifie que tous les modules fonctionnent ensemble.

### Contexte
Projet pushé sur GitHub, 80+ fichiers modifiés. Vérifier la cohérence globale.

### Tests d'Intégration à Effectuer

1. **Import Test** — Tous les modules s'importent sans erreur ?
```python
from autobot.v2.main_async import main
from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.strategy_ensemble import StrategyEnsemble
# etc.
```

2. **Instanciation Test** — Créer une instance complète :
```python
# Orchestrator + Instance + StrategyEnsemble + Modules
```

3. **Flow End-to-End** — Simuler un tick:
```
WebSocket → RingBuffer → Dispatcher → Instance → Strategy → Signal → OrderRouter
```

4. **Compatibilité** — Async/sync ne se mélangent pas ?

5. **Configuration** — .env.example complet ?

### Fichiers à vérifier
- src/autobot/v2/main_async.py (point d'entrée)
- src/autobot/v2/orchestrator_async.py (wiring)
- src/autobot/v2/strategy_ensemble.py (intégration stratégies)
- src/autobot/v2/modules/*.py (tous les modules)

### Livrables
- Liste des erreurs d'import/intégration
- Liste des incohérences
- Liste des paramètres manquants
- Commande pour tester le démarrage
