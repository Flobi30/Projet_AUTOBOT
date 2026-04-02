# AUTOBOT V2 — Refonte Architecture Asyncio Haute Performance

## Objectif
Passer de 50 à 2000+ instances avec latence sub-ms.
Migration threading → asyncio + uvloop.

## État actuel analysé
- **20,679 lignes** de code Python dans 54 fichiers
- **Threading partout**: Lock, RLock, Thread, Event dans 35+ fichiers
- **WebSocket**: `websocket-client` (sync) + threads de dispatch
- **HTTP**: `krakenex` (sync `requests`)
- **Persistance**: SQLite avec threading.Lock
- **4 tests** existants (test_order_executor, test_kelly_criterion, test_kraken_api, test_auto_evolution)

## Architecture cible
```
                    ┌─────────────────────────────┐
                    │       uvloop event loop       │
                    └──────────┬──────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                      │
    ┌────▼─────┐       ┌──────▼──────┐        ┌──────▼──────┐
    │ WebSocket │       │   Order     │        │   Cold Path  │
    │ (websockets│       │   Router    │        │   (logging,  │
    │  async)   │       │  (P1)       │        │    stats, DB)│
    └────┬─────┘       └──────▲──────┘        └─────────────┘
         │                     │
    ┌────▼─────┐       ┌──────┴──────┐
    │Ring Buffer│       │  asyncio    │
    │ (P2)     │────►  │  Queues     │
    └──────────┘       │  per inst.  │
                       │  (P3)       │
                       └──────┬──────┘
                              │
                    ┌─────────▼─────────┐
                    │  2000+ Instances   │
                    │  (async coroutines)│
                    └───────────────────┘
```

---

## P0 — MIGRATION ASYNCIO + UVLOOP (Fondement)
**Durée estimée**: 3-4 semaines | **Priorité**: CRITIQUE

### P0.1 — Core Event Loop & Orchestrator
- [x] Créer `orchestrator_async.py`: Orchestrator full asyncio
  - `async def start()`, `async def stop()`
  - `asyncio.Lock` au lieu de `threading.Lock`
  - `asyncio.Event` au lieu de `threading.Event`
  - `asyncio.create_task()` au lieu de `Thread(target=...)`
  - Main loop: `asyncio.sleep()` au lieu de `time.sleep()`
- [x] Intégrer uvloop comme event loop policy
- [x] Créer `main_async.py` avec `asyncio.run()`

### P0.2 — WebSocket Async
- [x] Créer `websocket_async.py`: KrakenWebSocket full async
  - Utilise `websockets` (async) au lieu de `websocket-client`
  - `async for message in websocket:` au lieu de callbacks threads
  - `asyncio.Queue` au lieu de dispatch thread
  - Reconnexion automatique avec backoff
  - WebSocketMultiplexer async (dispatch via asyncio.Queue)
- [x] TickerData inchangé (dataclass, pas de threading)

### P0.3 — Instance Async
- [x] Créer `instance_async.py`: TradingInstance full async
  - `async def on_price_update(data)` 
  - `async def open_position()`, `async def close_position()`
  - `asyncio.Lock` au lieu de `threading.Lock`
  - Persistence calls: `await loop.run_in_executor(None, sync_func)`
  - Recovery state: async-compatible

### P0.4 — OrderExecutor Async
- [x] Créer `order_executor_async.py`: OrderExecutor full async
  - `aiohttp.ClientSession` au lieu de `krakenex` (requests)
  - `async def execute_market_order()`
  - `async def execute_stop_loss_order()`
  - `asyncio.Lock` au lieu de `threading.RLock`
  - Rate limiting: `asyncio.sleep()` au lieu de `time.sleep()`
  - Circuit breaker: async-compatible

### P0.5 — Support Modules Async
- [x] `signal_handler_async.py`: SignalHandler async
- [x] `stop_loss_manager_async.py`: StopLossManager async
- [x] `reconciliation_async.py`: ReconciliationManager async
- [x] `order_queue_async.py`: OrderQueue async (asyncio.PriorityQueue)
- [x] `risk_manager.py`: Pas de threading, juste calculs → garder tel quel
- [x] `validator.py`: Pas de threading lourd → garder, enlever locks inutiles
- [x] `persistence.py`: Wrapper async (run_in_executor pour SQLite)

### P0.6 — Strategies Async
- [x] `strategies/__init__.py`: Strategy base → `async def on_price()`
- [x] `strategies/grid_async.py`: GridStrategy async
- [x] `strategies/trend_async.py`: TrendStrategy async
- [x] Modules (rate_limit_optimizer, etc.): calculs purs → garder tels quels

### P0.7 — Tests Migration
- [ ] Créer suite pytest-asyncio pour chaque module async
- [ ] Benchmark avant/après (latence, throughput)
- [ ] Tests d'intégration async end-to-end

### Fichiers créés (nouveaux, l'ancien code reste intact):
```
src/autobot/v2/
├── orchestrator_async.py    ← NEW
├── websocket_async.py       ← NEW
├── instance_async.py        ← NEW
├── order_executor_async.py  ← NEW
├── signal_handler_async.py  ← NEW
├── stop_loss_manager_async.py ← NEW
├── reconciliation_async.py  ← NEW
├── order_queue_async.py     ← NEW
├── main_async.py            ← NEW
├── strategies/
│   ├── __init_async__.py    ← NEW (Strategy base async)
│   ├── grid_async.py        ← NEW
│   └── trend_async.py       ← NEW
└── tests/
    ├── test_orchestrator_async.py  ← NEW
    ├── test_websocket_async.py     ← NEW
    ├── test_instance_async.py      ← NEW
    └── test_order_executor_async.py ← NEW
```

### Contraintes P0
- **Zero regression**: Le code threading existant reste intact
- **API publique identique**: Mêmes noms de méthodes, mêmes signatures (avec async)
- **Compatibilité**: Les modules sans threading (calculs purs) sont réutilisés directement

---

## P1 — ORDER ROUTER CENTRAL + RATE LIMIT (3-4 jours)
**Dépend de**: P0

- [ ] Créer `order_router.py`: Point unique d'accès API Kraken
- [ ] Intégrer `RateLimitOptimizer` existant dans le router
- [ ] File d'attente prioritaire: `asyncio.PriorityQueue`
  - EMERGENCY (SL) → priorité 0
  - ORDER (buy/sell) → priorité 1
  - INFO (balance, status) → priorité 2
- [ ] Protection ban API: toutes les instances passent par le routeur
- [ ] Interface: `await router.submit(order, priority)`
- [ ] Tests unitaires

---

## P2 — RING BUFFER LOCK-FREE ✅ TERMINÉ
**Dépend de**: P0

- [x] Créer `ring_buffer.py`: Shared memory SPMC
- [x] Index atomique via GIL CPython (asyncio single-thread — multiprocessing.Value non nécessaire)
- [x] Single Producer (WebSocket ingestion) → writes (~145 ns/op)
- [x] Multiple Consumers (worker tasks) → reads (~121 ns/msg amortisé)
- [x] Latence write: 145 ns, read_at: 218 ns, round-trip: 369 ns (CPython max ~150 ns)
- [x] Remplacer WebSocketMultiplexer dispatch → RingBufferDispatcher (ring_buffer_dispatcher.py)
- [x] Benchmarks mesurés: 2000 readers × 1000 ticks = 225 ns/reader/tick
- [x] 41 tests passent (correctness + perf + dispatcher + SPMC 2000 instances)

### Fichiers créés
- `src/autobot/v2/ring_buffer.py`          — RingBuffer + RingBufferReader, SPMC lock-free
- `src/autobot/v2/ring_buffer_dispatcher.py` — WebSocket → Ring → Instances dispatch
- `src/autobot/v2/tests/test_ring_buffer.py`  — 41 tests (correctness + benchmarks)

### Intégration orchestrateur (orchestrator_async.py)
- `self.ring_dispatcher = RingBufferDispatcher(...)` remplace WebSocketMultiplexerAsync
- `ring_dispatcher.subscribe(pair, instance_id)` → retourne RingBufferReader
- `asyncio.create_task(ring_dispatcher.run_consumer(id, callback))` → 1 task/instance
- `ring_dispatcher.unsubscribe(id)` + task.cancel() sur remove_instance

### Performances mesurées (CPython 3.11.2, Linux)
| Opération              | Latence    | Cible     |
|------------------------|------------|-----------|
| `write()`              | 145 ns/op  | <1 µs ✅  |
| `read_at()`            | 218 ns/op  | <500 ns ✅ |
| `write + poll()`       | 369 ns/op  | <800 ns ✅ |
| `poll_batch(64)` /msg  | 121 ns/msg | <200 ns ✅ |
| 2000 readers/tick      | 225 ns     | —         |

---

## P3 — DISPATCH ASYNC (2-3 jours)
**Dépend de**: P0, P2

- [ ] Une `asyncio.Queue` par instance
- [ ] Découplage: WS → Queue → Instance
- [ ] Non-bloquant, O(1) dispatch
- [ ] Backpressure handling (queue full → log warning, drop oldest)
- [ ] Tests latence

---

## P4 — HOT/COLD PATH SEPARATION ✅ TERMINÉ
**Dépend de**: P0, P3

- [x] Hot path: WS recv → parse → ring.write() → queue.put() → on_price_update()
  - Zéro asyncio.Lock (asyncio single-threaded — pas de contention possible)
  - Zéro I/O — data.timestamp réutilisé depuis TickerData (une seule alloc par msg WS)
  - No GC pressure — gc.disable() via HotPathOptimizer
  - Pre-allocation buffers: array.array("q") pré-alloué pour les échantillons de latence
- [x] Cold path: logging, stats, DB, risk
  - `asyncio.create_task()` fire-and-forget via ColdPathScheduler
  - check_leverage_downgrade() déplacé vers tâche périodique (60 s) — plus par tick
  - GC périodique toutes les 30 s via ColdPathScheduler.schedule_gc()
- [x] Profiling hot path: HotPathOptimizer.start_tick() / record_tick() / stats (P50/P95/P99)

### Fichiers créés
- `src/autobot/v2/hot_path_optimizer.py`   — GC control + latency ring buffer
- `src/autobot/v2/cold_path_scheduler.py`  — Fire-and-forget + periodic tasks
- `src/autobot/v2/tests/test_hot_cold_path.py` — 38 tests (GC + latency + hot/cold + integration)

### Fichiers modifiés
- `src/autobot/v2/instance_async.py`       — on_price_update: lock supprimé, check_leverage retiré
- `src/autobot/v2/orchestrator_async.py`   — Intégration hot_optimizer + cold_scheduler
- `src/autobot/v2/websocket_async.py`      — import datetime déplacé au niveau module

### Performances mesurées (CPython 3.11.2, Linux)
| Opération                    | Latence    | Cible     |
|------------------------------|------------|-----------|
| `on_price_update()` avg      | 0.24 µs    | <1 µs ✅  |
| `on_price_update()` P50      | 0.21 µs    | <1 µs ✅  |
| `on_price_update()` P95      | 0.25 µs    | <1 µs ✅  |
| `on_price_update()` P99      | 1.08 µs    | <10 µs ✅ |
| `record_tick()` overhead P99 | <1 µs      | <1 µs ✅  |

---

## P5 — TUNING OS-LEVEL ✅ TERMINÉ (2026-04-02)
**Dépend de**: P0-P4

- [x] `TCP_NODELAY` sur WebSocket connections
- [x] `SO_BUSY_POLL` si disponible (Linux ≥ 4.5, numeric fallback 46)
- [x] `TCP_QUICKACK` (Linux-only, via setsockopt)
- [x] CPU pinning: `os.sched_setaffinity()`
- [x] `SCHED_FIFO` pour priorité temps réel (opt-in, nécessite root)
- [x] `gc.disable()` déjà fait en P4 — pas dupliqué
- [x] Script sysctl Linux (`sysctl_config.sh` — apply/dry-run/restore)
- [x] Auto-détection capacités + logging + never raises

### Fichiers créés
- `src/autobot/v2/os_tuning.py`         — OSTuner + TuningResult + singleton
- `src/autobot/v2/sysctl_config.sh`     — Script kernel tuning (bash, documenté)
- `src/autobot/v2/tests/test_os_tuning.py` — 47 tests (mock syscall)

### Fichiers modifiés
- `src/autobot/v2/websocket_async.py`   — tune_websocket() après connect() + reconnect()
- `src/autobot/v2/main_async.py`        — _apply_os_tuning() au démarrage

---

## P6 — EXÉCUTION SPÉCULATIVE ✅ TERMINÉ (2026-04-02)
**Dépend de**: P0-P5

- [x] Pre-compute ordres BUY/SELL à chaque tick → cache
- [x] Templates pré-alloués (`bytearray` + `OrderTemplate` frozen dataclass)
- [x] Patch dynamique volume à offsets fixes (`_write_volume_to_buf` zero-alloc)
- [x] Envoi immédiat quand signal fire via `submit_speculative()` + `FastOrderBuilder`
- [x] Benchmarks: cache.get() hit = 154 ns, build_dict_only() = 580 ns

### Fichiers créés
- `src/autobot/v2/speculative_order_cache.py`  — OrderTemplate + SpeculativeOrderCache
- `src/autobot/v2/fast_order_builder.py`        — FastOrderBuilder + _write_volume_to_buf
- `src/autobot/v2/tests/test_speculative_execution.py` — 51 tests

### Fichiers modifiés
- `src/autobot/v2/order_router.py`              — set_speculative_cache() + submit_speculative()
- `src/autobot/v2/strategies/grid_async.py`     — attach_speculative_cache() + auto-precompute

### Performances mesurées (CPython 3.11.2, Linux)
| Opération                        | Latence    | Cible     |
|----------------------------------|------------|-----------|
| `cache.get()` hit                | 154 ns/op  | <1 µs ✅  |
| `cache.get()` miss               | 134 ns/op  | <1 µs ✅  |
| `build_dict_only()` (cache hit)  | 580 ns/op  | <1 µs ✅  |
| Template BUY: capital/price      | ~50 ns     | O(1) ✅   |
| SELL: volume pré-calculé         | 0 ns       | O(1) ✅   |

### Note CPython
`_write_volume_to_buf` (Python integer loop) = 789 ns/op vs `f"{v:.8f}"` = 110 ns/op.
CPython's built-in f-string (C-level) est 7x plus rapide que le loop Python.
→ `_params_dict` utilise f-string; `_write_volume_to_buf` réservé aux body bytes.

---

## Métriques de succès
| Métrique | Avant (threading) | Cible (asyncio) |
|---|---|---|
| Max instances | 50 | 2000+ |
| Latence tick→signal | ~1-10ms | <100μs |
| Latence signal→ordre | ~50ms | <1ms |
| Memory per instance | ~5MB | <500KB |
| CPU usage 50 inst | 30%+ | <5% |
| WebSocket connections | N (1 per pair) | 1 (multiplexed) |

---

## Notes de migration
- **Approche**: Fichiers parallèles (_async.py), pas de modification des fichiers existants
- **Transition**: Les tests vérifient que le comportement est identique
- **Rollback**: Supprimer les fichiers _async.py pour revenir à l'ancien code
- **Production**: Swapper les imports quand tous les tests passent
