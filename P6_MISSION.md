## MISSION: Implémenter P6 — Exécution Spéculative pour AutoBot V2 Async

### Contexte
P0 (Migration Asyncio) ✅ TERMINÉ
P1 (Order Router) ✅ TERMINÉ — 37 tests
P2 (Ring Buffer Lock-Free) ✅ TERMINÉ — 41 tests
P3 (Dispatch Async) ✅ TERMINÉ — 39 tests
P4 (Hot/Cold Path) ✅ TERMINÉ — 38 tests, P99: 1.08µs
P5 (OS Tuning) ✅ TERMINÉ — 47 tests

### Objectif P6
Pré-calculer les ordres à chaque tick pour envoi immédiat quand le signal fire.
Zero compute entre signal et envoi ordre.

### Spécifications techniques

1. **OrderTemplate** — Template d'ordre pré-calculé
   - Structure fixe: type, symbol, side, volume placeholders
   - Sérialisé en bytes une seule fois
   - Patch rapide: prix/volume à offsets connus

2. **SpeculativeOrderCache** — Cache de templates
   - Clé: (symbol, side, strategy_type)
   - Valeur: template bytes + offsets
   - Pré-compute pour BUY/SELL à chaque niveau Grid

3. **FastOrderBuilder** — Construction zéro-alloc
   - Reçoit signal → récupère template → patch prix/volume
   - Retourne bytes prêts à envoyer
   - Pas de json.dumps(), pas de string format

4. **Intégration OrderRouter**
   - Routeur vérifie cache avant construction
   - Hit: template patché → envoi immédiat
   - Miss: construction classique (fallback)

### Fichiers à créer
1. src/autobot/v2/speculative_order_cache.py — Cache templates
2. src/autobot/v2/fast_order_builder.py — Patch zéro-alloc
3. src/autobot/v2/tests/test_speculative_execution.py — Tests

### Fichiers à modifier
- src/autobot/v2/order_router.py — Intégrer cache
- src/autobot/v2/strategies/grid_async.py — Pré-compute templates

### Contraintes
- Latence signal→ordre: <1ms (objectif <100µs)
- Zero allocation pendant hot path
- Templates immutables, thread-safe
- Fallback si cache miss
- Tests: benchmark hit vs miss

### Références
- /home/node/.openclaw/workspace/src/autobot/v2/PLAN_TODO.md (section P6)
- /home/node/.openclaw/workspace/src/autobot/v2/order_router.py
- /home/node/.openclaw/workspace/src/autobot/v2/strategies/grid_async.py

### Livrables
1. Code exécution spéculative avec docstrings
2. Tests: cache hit/miss, benchmarks latence
3. Résumé gains (µs gagnés par ordre)
4. Signal fin P0-P6 complet
