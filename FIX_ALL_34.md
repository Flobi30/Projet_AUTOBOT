## MISSION: Corrections COMPLÈTES — 11 Critiques + 23 Warnings (34 total)

## 🔴 CRITIQUES (11)

### ROB-01 — Write-Ahead Log ordres (anti-double achat)
Fichiers: signal_handler.py, order_executor_async.py

### SEC-02 — Dashboard HTTPS
Fichier: api/dashboard.py

### ARCH-01 — asyncio.Lock sur _instances
Fichier: orchestrator_async.py

### ROB-02 — Stop-loss orphelins
Fichier: signal_handler.py

### SEC-03 — Nonce monotone
Fichier: order_executor_async.py

### SEC-01 — Masquer API secrets
Fichiers: orchestrator*.py

### ARCH-02 — Vérification ressources avant création instance
Fichier: orchestrator_async.py

### ARCH-03 — Pool connexions SQLite
Fichier: persistence.py

### SEC-04 — sys.path sécurisé
Fichier: main_async.py

### SEC-05 — sysctl_config.sh warnings
Fichier: sysctl_config.sh

### PROD-01 — Health check
Fichier: main_async.py

## 🟡 WARNINGS (23)

### SEC-06 — CORS restreint en prod
dashboard.py

### SEC-07 — Auth bypass log ERROR
dashboard.py

### SEC-08 — Validation shape réponses Kraken
order_executor.py

### SEC-09 — Stack traces masquées en prod
Multiple

### SEC-10 — DB SQLite chiffrée
persistence.py

### SEC-11 — SCHED_FIFO watchdog
os_tuning.py

### SEC-12 — Rotation clés API
orchestrator*.py

### SEC-13 — /health limité
api/dashboard.py

### ARCH-04 — Duplication sync/async
Multiple fichiers

### ARCH-05 — Singletons non-reset entre tests
Multiple

### ARCH-06 — ReconciliationManager snapshot statique
reconciliation.py

### ARCH-07 — check_leverage_downgrade hot path
instance.py vs async

### ARCH-08 — Backpressure WS monitoring
websocket_async.py

### ARCH-09 — _get_available_capital_real bloquant
instance.py

### ROB-03 — Circuit breaker WebSocket
websocket_async.py

### ROB-04 — _close_all_positions_market krakenex direct
instance.py

### ROB-05 — _cancel_all_orders krakenex direct
instance.py

### ROB-06 — ReconciliationManager appelle _safe_api_call direct
reconciliation.py

### ROB-07 — Graceful shutdown perd des ticks
async_dispatcher.py

### PROD-02 — Metrics Prometheus/StatsD
Global

### PROD-03 — Alerting structuré
Global

### PROD-04 — Backup SQLite toutes les heures
persistence.py

### PROD-05 — Tests intégration mock Kraken
Global

## Livrables
1. Tous les fichiers corrigés
2. Tests mis à jour et passants
3. Documentation des changements
