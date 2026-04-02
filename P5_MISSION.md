## MISSION: Implémenter P5 — OS Tuning pour AutoBot V2 Async

### Contexte
P0 (Migration Asyncio) ✅ TERMINÉ
P1 (Order Router) ✅ TERMINÉ — 37 tests
P2 (Ring Buffer Lock-Free) ✅ TERMINÉ — 41 tests
P3 (Dispatch Async) ✅ TERMINÉ — 39 tests
P4 (Hot/Cold Path) ✅ TERMINÉ — 38 tests, P99: 1.08µs

### Objectif P5
Optimisations OS-level pour réduire la latence réseau et améliorer la stabilité temps réel.

### Spécifications techniques

1. **TCP Tuning**
   - TCP_NODELAY sur WebSocket connections (désactive Nagle)
   - SO_BUSY_POLL si disponible (Linux kernel 4.5+)
   - TCP_QUICKACK pour ACK immédiats

2. **CPU Pinning**
   - os.sched_setaffinity() pour binder le process sur des cœurs dédiés
   - Isoler le thread hot path des interruptions

3. **Real-Time Scheduling**
   - SCHED_FIFO pour priorité temps réel
   - Attention: nécessite root ou CAP_SYS_NICE

4. **Kernel Tuning**
   - Script sysctl pour:
     - net.ipv4.tcp_tw_reuse=1 (reuse TIME_WAIT sockets)
     - net.core.somaxconn=65535 (backlog connections)
     - vm.swappiness=1 (éviter swap)

5. **Auto-détection**
   - Détecter si on a les droits root
   - Appliquer les optimisations disponibles
   - Logger ce qui a été activé

### Fichiers à créer
1. src/autobot/v2/os_tuning.py — Tuning TCP, CPU, scheduling
2. src/autobot/v2/sysctl_config.sh — Script kernel tuning
3. src/autobot/v2/tests/test_os_tuning.py — Tests (mock syscall)

### Fichiers à modifier
- src/autobot/v2/websocket_async.py — TCP_NODELAY sur connections
- src/autobot/v2/main_async.py — Appliquer tuning au démarrage

### Contraintes
- Ne pas planter si pas root (grâce aux droits)
- Auto-détection des capacités
- Logging clair de ce qui est activé
- Tests: mock os.* pour CI

### Références
- /home/node/.openclaw/workspace/src/autobot/v2/PLAN_TODO.md (section P5)
- /home/node/.openclaw/workspace/src/autobot/v2/websocket_async.py

### Livrables
1. Code tuning OS avec docstrings
2. Script sysctl documenté
3. Tests: vérifier tentative d'application
4. Signaler tout problème bloquant pour P6
