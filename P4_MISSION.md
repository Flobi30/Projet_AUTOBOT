## MISSION: Implémenter P4 — Hot/Cold Path Separation pour AutoBot V2 Async

### Contexte
P0 (Migration Asyncio) ✅ TERMINÉ
P1 (Order Router) ✅ TERMINÉ — 37 tests
P2 (Ring Buffer Lock-Free) ✅ TERMINÉ — 41 tests
P3 (Dispatch Async) ✅ TERMINÉ — 39 tests

### Objectif P4
Séparer clairement le hot path (latence critique) du cold path (tâches non-critiques).

**Hot Path (zéro I/O, zéro allocation):**
WebSocket recv → parse → ring.write() → dispatch → queue.put() → on_price_update()

**Cold Path (fire-and-forget):**
- SQLite persistence (save_state)
- Logging verbose
- Risk checks périodiques
- Analytics/métriques

### Spécifications techniques

1. **HotPathOptimizer**
   - Désactive GC sur le hot path: gc.disable()
   - Pre-allocation des buffers
   - Zéro appel système bloquant
   - Mesure temps de traitement (micro-benchmarks)

2. **ColdPathScheduler**
   - Tasks asyncio séparées (fire-and-forget)
   - Priorité basse: asyncio.create_task avec low priority
   - Batch processing quand possible
   - Ne jamais bloquer le hot path

3. **Modifications requises**
   - instance_async.py: séparer on_price_update (hot) de save_state (cold)
   - orchestrator_async.py: scheduler cold path tasks
   - websocket_async.py: parsing sans alloc

### Fichiers à créer
1. src/autobot/v2/hot_path_optimizer.py — Gestion GC, buffers
2. src/autobot/v2/cold_path_scheduler.py — Tasks fire-and-forget
3. src/autobot/v2/tests/test_hot_cold_path.py — Tests

### Fichiers à modifier
- src/autobot/v2/instance_async.py — Hot path optimisé
- src/autobot/v2/orchestrator_async.py — Intégrer scheduler

### Contraintes
- Hot path: <1μs par tick
- Cold path: jamais de await pendant hot path
- Profiling: cProfile ou py-spy
- Tests: benchmark latence avant/après

### Références
- /home/node/.openclaw/workspace/src/autobot/v2/PLAN_TODO.md (section P4)
- /home/node/.openclaw/workspace/src/autobot/v2/instance_async.py
- /home/node/.openclaw/workspace/src/autobot/v2/orchestrator_async.py

### Livrables
1. Code hot/cold path avec docstrings
2. Tests: benchmark latence hot path
3. Résumé gains de performance
4. Signaler tout problème bloquant pour P5
