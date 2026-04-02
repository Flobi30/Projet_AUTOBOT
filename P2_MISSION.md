## MISSION: Implémenter P2 — Ring Buffer Lock-Free pour AutoBot V2 Async

### Contexte
P0 (Migration Asyncio) ✅ TERMINÉ — 2000 instances, 555K ticks/sec
P1 (Order Router) ✅ TERMINÉ — PriorityQueue, 37 tests passent

### Objectif P2
Créer un Ring Buffer lock-free SPMC (Single Producer / Multiple Consumers) pour remplacer le dispatch WebSocket actuel.

**Architecture cible:**
- Single Producer: WebSocket ingestion (1 thread écrit)
- Multiple Consumers: worker tasks (N tasks lisent)
- Latence cible: <100ns par message
- Pas de locks, pas de GC pressure

### Spécifications techniques
1. **RingBuffer** — Buffer circulaire lock-free
   - Taille: 2^n (ex: 65536 slots) pour masque bitwise
   - Slot: (seq: int, data: bytes/data class)
   - Producteur incrémente write_seq
   - Consommateurs lisent read_seq
   - Wait-free: si buffer full, overwrite oldest (pas de blocage)

2. **WebSocket → RingBuffer**
   - Remplacer WebSocketMultiplexerAsync
   - Parse JSON → sérialise en bytes → écrit dans ring

3. **RingBuffer → Instances**
   - Chaque instance a son propre read_seq
   - Poll non-bloquant: while reader.read(seq): process()
   - Batch read possible (plusieurs messages d'un coup)

### Fichiers à créer
1. src/autobot/v2/ring_buffer.py — RingBuffer lock-free
2. src/autobot/v2/ring_buffer_dispatcher.py — WebSocket → Ring → Instances
3. src/autobot/v2/tests/test_ring_buffer.py — Tests (correctness, perf)

### Fichiers à modifier
- src/autobot/v2/websocket_async.py — Utiliser RingBuffer au lieu de Queue
- src/autobot/v2/orchestrator_async.py — Intégrer RingBufferDispatcher

### Contraintes
- Lock-free: pas de threading.Lock, pas de asyncio.Lock
- Memory pre-allocated: pas d'allocation pendant le hot path
- Calcul O(1): masque bitwise index = seq & (size-1)
- Zero-copy quand possible
- Tests: correctness (seq ordering) + perf (latency <100ns)
- Python 3.11+ compatible

### Références à lire
- /home/node/.openclaw/workspace/src/autobot/v2/PLAN_TODO.md (section P2)
- /home/node/.openclaw/workspace/src/autobot/v2/websocket_async.py (WebSocketMultiplexerAsync)
- /home/node/.openclaw/workspace/src/autobot/v2/orchestrator_async.py (dispatch actuel)
- /home/node/.openclaw/workspace/src/autobot/v2/order_router.py (style de code attendu)

### Livrables
1. Code lock-free avec docstrings
2. Tests: correctness + benchmark latency
3. Résumé performance (ns/op)
4. Signaler tout problème bloquant pour P3
