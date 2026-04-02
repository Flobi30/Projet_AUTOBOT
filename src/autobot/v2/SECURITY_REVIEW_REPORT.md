# 🔒 RAPPORT DE REVIEW SÉCURITÉ & ARCHITECTURE — AUTOBOT V2

**Date :** 2026-04-02  
**Scope :** `src/autobot/v2/` — 84+ fichiers Python, 1 Bash, ~12 000+ lignes  
**Méthodologie :** Analyse statique approfondie, OWASP adaptée trading, review architecture  

---

## 📊 RÉSUMÉ EXÉCUTIF

| Catégorie | 🔴 CRITIQUE | 🟡 WARNING | 🟢 INFO |
|-----------|:-----------:|:----------:|:-------:|
| Sécurité | 5 | 8 | 4 |
| Architecture | 3 | 6 | 5 |
| Robustesse | 2 | 5 | 3 |
| Production | 1 | 4 | 3 |
| **TOTAL** | **11** | **23** | **15** |

**Verdict :** Projet bien structuré avec de bonnes pratiques déjà en place (thread-safety, circuit breaker, WAL SQLite, atomic ops). **11 critiques** à résoudre avant prod avec argent réel.

---

## 🔴 CRITIQUES (11) — BLOQUANTS PRODUCTION

### SEC-01 🔴 Clés API en clair dans toute la chaîne d'objets
**Fichiers :** orchestrator*.py, order_executor*.py, instance.py  
`api_key`/`api_secret` stockés comme attributs dans 5+ classes. Compromission totale si dump mémoire ou log de debug avec stack trace.  
**Fix :** CredentialProvider lazy, zeroing après usage, `__repr__` masquant les secrets.

### SEC-02 🔴 Dashboard API sur HTTP — Token Bearer en clair
**Fichier :** api/dashboard.py  
Endpoints critiques (emergency-stop, positions, capital) sans TLS.  
**Fix :** TLS obligatoire (Let's Encrypt/reverse proxy), HSTS, rate limiting, IP whitelist.

### SEC-03 🔴 Nonce HMAC prévisible (`time.time()*1000`)
**Fichier :** order_executor_async.py L74  
Prévisible et potentiellement non-monotone (NTP).  
**Fix :** Compteur monotone persisté, incrémenté sous lock.

### SEC-04 🔴 `sys.path.insert(0, ...)` — injection de modules possible
**Fichiers :** main.py L14, main_async.py L17  
**Fix :** Package installé via `pip install -e .`

### SEC-05 🔴 `sysctl_config.sh` — modifications kernel persistantes non-sécurisées
Script root modifiant vm.swappiness, somaxconn, tcp_tw_reuse. Le `--persist` survit au reboot.  
**Fix :** Double confirmation, jamais automatique, review humaine obligatoire.

### ARCH-01 🔴 Pas de lock asyncio sur `_instances` dans OrchestratorAsync
**Fichier :** orchestrator_async.py  
Contrairement au sync (qui a `_instance_lock`), l'async n'a aucun Lock. Les `await` dans create/remove_instance créent des race conditions TOCTOU.  
**Fix :** `asyncio.Lock()` autour des sections critiques.

### ARCH-02 🔴 `max_instances: 2000` sans validation de ressources
**Fichier :** orchestrator_async.py L73  
Aucune vérification RAM/CPU/FDs avant création. ~2-4 GB RAM estimé pour 2000 instances.  
**Fix :** Health check mémoire avant chaque création, limite dynamique.

### ARCH-03 🔴 SQLite : nouvelle connexion + lock global à chaque appel
**Fichier :** persistence.py  
`sqlite3.connect()` sous `threading.Lock` à chaque write. Goulot avec 2000 instances.  
**Fix :** Connexion persistante, batch writes, `aiosqlite` pour async.

### ROB-01 🔴 Pas de write-ahead log — risque de double achat après crash
**Fichiers :** signal_handler.py, order_executor.py  
Crash entre envoi ordre Kraken et save_position → au restart, double achat.  
**Fix :** WAL : écrire intention AVANT appel API. Réconciliation immédiate au restart. Utiliser `userref` Kraken.

### ROB-02 🔴 Stop-loss orphelin après fermeture de position
**Fichier :** signal_handler.py L164  
Si `cancel_order(SL)` échoue mais position fermée localement → SL actif vend la prochaine position.  
**Fix :** Retry backoff, ne fermer localement qu'APRÈS confirmation annulation SL.

### PROD-01 🔴 Pas de health check pour le async entry point
**Fichier :** main_async.py  
`main.py` démarre un dashboard avec `/health`, mais `main_async.py` n'a pas de serveur HTTP ni de health check.  
**Fix :** Intégrer un serveur ASGI (FastAPI) dans la version async aussi.

---

## 🟡 WARNINGS (23) — RISQUES ÉLEVÉS

### Sécurité (8)

**SEC-06 🟡** CORS origins hardcodées localhost — configurer via env var en prod  
**SEC-07 🟡** Mode dev bypass auth silencieusement — ajouter log ERROR + bannière  
**SEC-08 🟡** Pas de validation shape réponses Kraken — `response['result']['txid'][0]` crash si format change  
**SEC-09 🟡** `logger.exception()` expose stack traces en prod — logger DEBUG + message générique ERROR  
**SEC-10 🟡** DB SQLite non chiffrée (positions, capital, trades en clair sur disque) — SQLCipher  
**SEC-11 🟡** `SCHED_FIFO` peut geler le système si boucle infinie — watchdog obligatoire  
**SEC-12 🟡** Pas de rotation clés API — mécanisme de reload à chaud (SIGHUP)  
**SEC-13 🟡** `/health` non-authentifié expose infos de reconnaissance — limiter à `{"ok":true}`  

### Architecture (6)

**ARCH-04 🟡** Duplication massive sync/async (~12 fichiers dupliqués) — maintenance double, bugs fixés d'un côté seulement. Migrer full async.  
**ARCH-05 🟡** Singletons globaux non-reset entre tests — fuite d'état possible  
**ARCH-06 🟡** ReconciliationManager reçoit snapshot statique des instances — nouvelles instances jamais réconciliées  
**ARCH-07 🟡** `check_leverage_downgrade` hot path (sync) vs cold path (async) — incohérence  
**ARCH-08 🟡** Pas de backpressure WS → instance pipeline — monitoring lag manquant  
**ARCH-09 🟡** `_get_available_capital_real()` appel API bloquant dans main loop sync  

### Robustesse (5)

**ROB-03 🟡** Pas de circuit breaker sur WebSocket (existe sur OrderExecutor seulement)  
**ROB-04 🟡** `_close_all_positions_market()` dans instance.py crée un nouveau `krakenex.API` au lieu d'utiliser OrderExecutor  
**ROB-05 🟡** `_cancel_all_orders()` idem — devrait passer par OrderExecutor pour rate limiting centralisé  
**ROB-06 🟡** ReconciliationManager._get_kraken_orders appelle `_safe_api_call` directement au lieu de OrderExecutor public API  
**ROB-07 🟡** Graceful shutdown de l'async dispatcher peut perdre des ticks en queue si une instance est lente à drain  

### Production (4)

**PROD-02 🟡** Pas de metrics Prometheus/StatsD — impossible de monitorer en prod  
**PROD-03 🟡** Pas de structured alerting (PagerDuty, Slack webhook) — seulement des logs  
**PROD-04 🟡** Backup SQLite toutes les 24h — trop espacé pour un trading bot (risque perte 24h de données)  
**PROD-05 🟡** Pas de test d'intégration avec mock Kraken — tests unitaires seulement  

---

## 🟢 INFO (15) — AMÉLIORATIONS

### Sécurité (4)
- **SEC-14** Ajouter Content-Security-Policy headers sur le dashboard
- **SEC-15** Log d'audit pour toutes les actions API (qui a fait quoi, quand)
- **SEC-16** 2FA pour les actions critiques du dashboard (emergency stop)
- **SEC-17** Expiration automatique du token Bearer (JWT avec TTL)

### Architecture (5)
- **ARCH-10** `InstanceConfig` dataclass sans validation — Pydantic serait mieux
- **ARCH-11** Symbol mapping hardcodé dans 3 endroits différents — centraliser
- **ARCH-12** `_KRAKEN_SYMBOL_MAP` ne couvre que 12 paires — auto-discovery via API
- **ARCH-13** Strategy factory pattern au lieu de if/elif chain dans `_init_strategy`
- **ARCH-14** Le fee optimizer ne rafraîchit pas les frais Kraken dynamiquement (tier progression)

### Robustesse (3)
- **ROB-08** `detect_trend()` utilise SMA simple — considérer EMA pour moins de lag
- **ROB-09** `_compute_profit_factor_days()` itère toute la deque à chaque appel — cacher le résultat
- **ROB-10** Le BlackSwanCatcher Welford accumule une dérive numérique sur très longues sessions — reset périodique

### Production (3)
- **PROD-06** Ajouter `__version__` dans `__init__.py` pour traçabilité des déploiements
- **PROD-07** Containerization (Dockerfile) pour déploiement reproductible
- **PROD-08** Runbook documenté : procédure de récupération après crash, failover, rollback

---

## 🎯 POINTS POSITIFS IDENTIFIÉS

Le projet intègre déjà de nombreuses bonnes pratiques :

1. ✅ **Circuit breaker** sur OrderExecutor (10 erreurs → emergency stop)
2. ✅ **SQLite WAL mode** + busy_timeout pour concurrence
3. ✅ **Opérations atomiques** (close_position_and_record_trade)
4. ✅ **Thread-safety** systématique (locks, copies sous lock, callbacks hors lock)
5. ✅ **Deques bornées** pour éviter fuite mémoire (price_history, trades)
6. ✅ **Validation avant trading** (ValidatorEngine, open_position checks)
7. ✅ **Stop-loss Kraken** (côté exchange, pas logiciel)
8. ✅ **Shadow trading** avec période de validation avant promotion live
9. ✅ **Backoff exponentiel** sur retry API
10. ✅ **Hot/Cold path séparation** (P4) pour optimiser la latence
11. ✅ **Ring buffer + async dispatch** (P2/P3) pour découpler WS des instances
12. ✅ **Price validation** (NaN, Inf, >10% jump rejection)
13. ✅ **Leverage downgrade automatique** si conditions non remplies
14. ✅ **Grid recentering** automatique si drift >5%
15. ✅ **Fee optimizer** dynamique au lieu de frais hardcodés

---

## 📋 PLAN D'ACTION PRIORISÉ

### Phase 1 — Avant premier EUR en production (1-2 semaines)

| # | Sévérité | ID | Action | Effort |
|---|----------|----|--------|--------|
| 1 | 🔴 | ROB-01 | Write-ahead log pour ordres (anti-double achat) | 3j |
| 2 | 🔴 | SEC-02 | TLS sur dashboard (reverse proxy ou uvicorn SSL) | 1j |
| 3 | 🔴 | ARCH-01 | asyncio.Lock sur _instances dans OrchestratorAsync | 0.5j |
| 4 | 🔴 | ROB-02 | Retry + confirmation annulation SL avant close local | 1j |
| 5 | 🔴 | SEC-03 | Nonce monotone persisté | 0.5j |
| 6 | 🔴 | SEC-01 | CredentialProvider (au minimum __repr__ masqué) | 1j |
| 7 | 🔴 | PROD-01 | Health check dans main_async.py | 0.5j |

### Phase 2 — Première semaine de trading (semaines 2-3)

| # | Sévérité | ID | Action | Effort |
|---|----------|----|--------|--------|
| 8 | 🔴 | ARCH-03 | Connexion SQLite persistante + batch writes | 2j |
| 9 | 🟡 | ARCH-06 | ReconciliationManager avec instances live (pas snapshot) | 1j |
| 10 | 🟡 | SEC-08 | Validation shape réponses Kraken | 1j |
| 11 | 🟡 | ROB-04/05 | Centraliser tous les appels Kraken via OrderExecutor | 2j |
| 12 | 🟡 | ARCH-02 | Health check mémoire avant création instance | 1j |
| 13 | 🟡 | PROD-02 | Metrics Prometheus/StatsD basiques | 2j |

### Phase 3 — Stabilisation (semaines 3-6)

| # | Sévérité | ID | Action | Effort |
|---|----------|----|--------|--------|
| 14 | 🟡 | ARCH-04 | Migration complète vers async (déprécier sync) | 5j |
| 15 | 🟡 | SEC-10 | Chiffrement SQLite (SQLCipher) | 1j |
| 16 | 🟡 | SEC-12 | Rotation clés API à chaud | 2j |
| 17 | 🟡 | PROD-03 | Alerting structuré (Slack/PagerDuty) | 1j |
| 18 | 🟡 | PROD-04 | Backup SQLite toutes les heures (pas 24h) | 0.5j |
| 19 | 🟡 | PROD-05 | Tests d'intégration avec mock Kraken | 3j |
| 20 | 🔴 | SEC-04 | Supprimer sys.path.insert, proper packaging | 1j |

### Phase 4 — Hardening (semaines 6+)

| # | Sévérité | ID | Action | Effort |
|---|----------|----|--------|--------|
| 21 | 🟢 | SEC-16 | 2FA pour emergency stop | 2j |
| 22 | 🟢 | ARCH-13 | Strategy factory pattern | 1j |
| 23 | 🟢 | ARCH-11 | Centraliser symbol mapping | 0.5j |
| 24 | 🟢 | PROD-07 | Dockerfile + docker-compose | 1j |
| 25 | 🟢 | PROD-08 | Runbook de récupération documenté | 1j |
| 26 | 🔴 | SEC-05 | Review sysctl_config.sh + safeguards | 0.5j |

---

## ⚡ TOP 5 QUICK WINS (impact maximal, effort minimal)

1. **`asyncio.Lock` sur _instances** (ARCH-01) — 30 min, élimine race condition critique
2. **TLS reverse proxy** (SEC-02) — 1h avec caddy/nginx, sécurise toute l'API
3. **`__repr__` masqué sur classes avec secrets** (SEC-01 partiel) — 30 min
4. **Nonce monotone** (SEC-03) — 30 min, élimine replay attacks
5. **Health check main_async** (PROD-01) — 1h, monitoring basique

---

## 📐 MATRICE DE RISQUE

```
        IMPACT
        ┃ ÉLEVÉ ┃ MOYEN  ┃ FAIBLE
━━━━━━━━╋━━━━━━━╋━━━━━━━━╋━━━━━━━
PROB.   ┃       ┃        ┃
ÉLEVÉE  ┃ROB-01 ┃ARCH-03 ┃SEC-09
        ┃ARCH-01┃ARCH-04 ┃
━━━━━━━━╋━━━━━━━╋━━━━━━━━╋━━━━━━━
PROB.   ┃SEC-02 ┃ROB-02  ┃SEC-13
MOYENNE ┃SEC-01 ┃ARCH-06 ┃PROD-04
        ┃SEC-03 ┃SEC-08  ┃
━━━━━━━━╋━━━━━━━╋━━━━━━━━╋━━━━━━━
PROB.   ┃SEC-05 ┃SEC-11  ┃ARCH-10
FAIBLE  ┃SEC-04 ┃ARCH-02 ┃ARCH-12
        ┃       ┃PROD-01 ┃
```

---

*Rapport généré par review sécurité/architecture approfondie. Prochaine review recommandée après implémentation Phase 1.*