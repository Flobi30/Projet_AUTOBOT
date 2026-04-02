## MISSION: Implémenter P3 — Dispatch Async pour AutoBot V2 Async

### Contexte
P0 (Migration Asyncio) ✅ TERMINÉ — 2000 instances, 555K ticks/sec
P1 (Order Router) ✅ TERMINÉ — PriorityQueue, 37 tests passent
P2 (Ring Buffer Lock-Free) ✅ TERMINÉ — SPMC, 41 tests passent, latence <100ns

### Objectif P3
Créer un système de dispatch async où chaque instance a sa propre asyncio.Queue.
- Découplage complet: WebSocket → Ring Buffer → Queues → Instances
- Dispatch O(1) non-bloquant
- Backpressure handling (queue full → log warning, drop oldest)

### Architecture cible
```
WebSocket
    ↓
RingBuffer (P2) — 1 producteur, N consumers
    ↓
AsyncDispatcher — lit RingBuffer, route vers queues
    ↓
asyncio.Queue (1 par instance) — buffer découplé
    ↓
TradingInstanceAsync — consume sa queue
```

### Spécifications techniques
1. **AsyncDispatcher** — Routeur de messages
   - Lit le RingBuffer en continu (poll non-bloquant)
   - Route les ticks vers les instances concernées
   - Gère les subscriptions (instances s'inscrivent pour une paire)
   - Skip si instance n'est pas intéressée par ce pair

2. **InstanceQueue** — Wrapper asyncio.Queue par instance
   - Taille max configurable (ex: 1000 messages)
   - Policy quand full: drop oldest ou block
   - Métriques: fill level, drop count

3. **TradingInstanceAsync** — Modification
   - Remplace on_price_update direct par consumption queue
   - Task asyncio dédiée pour consommer la queue
   - Graceful shutdown: vide la queue avant stop

### Fichiers à créer
1. src/autobot/v2/async_dispatcher.py — Dispatcher RingBuffer → Queues
2. src/autobot/v2/instance_queue.py — Wrapper asyncio.Queue par instance
3. src/autobot/v2/tests/test_async_dispatcher.py — Tests
4. src/autobot/v2/tests/test_instance_queue.py — Tests

### Fichiers à modifier
- src/autobot/v2/orchestrator_async.py — Intégrer AsyncDispatcher
- src/autobot/v2/instance_async.py — Utiliser queue au lieu de callback direct

### Contraintes
- O(1) dispatch: pas de scan de toutes les instances
- Non-bloquant: jamais de await pendant le routing
- Backpressure: métriques visibles, pas de crash
- Thread-safe: même pattern que P1/P2
- Tests: unitaires + intégration (end-to-end)

### Références à lire
- /home/node/.openclaw/workspace/src/autobot/v2/PLAN_TODO.md (section P3)
- /home/node/.openclaw/workspace/src/autobot/v2/ring_buffer.py (P2)
- /home/node/.openclaw/workspace/src/autobot/v2/ring_buffer_dispatcher.py (P2)
- /home/node/.openclaw/workspace/src/autobot/v2/orchestrator_async.py
- /home/node/.openclaw/workspace/src/autobot/v2/instance_async.py

### Livrables
1. Code async avec docstrings
2. Tests: unitaires + intégration end-to-end
3. Résumé architecture (diagramme texte)
4. Signaler tout problème bloquant pour P4
