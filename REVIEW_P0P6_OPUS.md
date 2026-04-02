## MISSION: Review Complète P0-P6 AutoBot V2 — Approche SÉCURITÉ

Tu es Claude Opus 4.6.

### Contexte
P0-P6 terminés:
- P0: Migration asyncio + uvloop
- P1: Order Router (37 tests)
- P2: Ring Buffer lock-free (41 tests)
- P3: Dispatch async (39 tests)
- P4: Hot/Cold Path (38 tests, P99: 1.08µs)
- P5: OS Tuning (47 tests)
- P6: Exécution Spéculative (253 tests totaux)

### Fichiers à reviewer
- /home/node/.openclaw/workspace/src/autobot/v2/*_async.py (tous)
- /home/node/.openclaw/workspace/src/autobot/v2/order_router.py
- /home/node/.openclaw/workspace/src/autobot/v2/ring_buffer.py
- /home/node/.openclaw/workspace/src/autobot/v2/ring_buffer_dispatcher.py
- /home/node/.openclaw/workspace/src/autobot/v2/async_dispatcher.py
- /home/node/.openclaw/workspace/src/autobot/v2/hot_path_optimizer.py
- /home/node/.openclaw/workspace/src/autobot/v2/cold_path_scheduler.py
- /home/node/.openclaw/workspace/src/autobot/v2/os_tuning.py
- /home/node/.openclaw/workspace/src/autobot/v2/speculative_order_cache.py
- /home/node/.openclaw/workspace/src/autobot/v2/fast_order_builder.py

### Questions
1. Y a-t-il des failles de sécurité dans l'architecture async?
2. Les locks sont-ils correctement gérés?
3. Y a-t-il des race conditions entre RingBuffer et OrderRouter?
4. Le hot path est-il vraiment isolé du cold path?
5. Des fuites mémoire possibles?
6. Gestion des erreurs robuste?

### Livrables
- Liste des problèmes 🔴 CRITIQUE / 🟡 WARNING / 🟢 INFO
- Priorité 1-10 pour chaque problème
- Recommandations de correction
