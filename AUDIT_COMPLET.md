# 🔍 AUDIT COMPLET — AutoBot V2

**Date :** 2 avril 2026  
**Scope :** `/src/autobot/v2/` — ~33 000 lignes, 70+ fichiers Python  
**Auditeur :** Subagent Claude Opus 4

---

## RÉSUMÉ EXÉCUTIF

| Catégorie | 🔴 CRITIQUE | 🟡 WARNING | 🟢 INFO |
|-----------|:-----------:|:----------:|:-------:|
| Architecture & Design | 2 | 4 | 3 |
| Code Quality | 1 | 5 | 4 |
| Sécurité | 3 | 3 | 2 |
| Infrastructure | 2 | 3 | 2 |
| Bugs Potentiels | 3 | 4 | 2 |
| Tests | 1 | 3 | 1 |
| Documentation | 0 | 2 | 3 |
| **TOTAL** | **12** | **24** | **17** |

**Verdict global :** Architecture mûre (P0→P5, hot/cold paths, ring buffers SPMC) avec de bonnes pratiques (circuit breaker, réconciliation, crash recovery). Cependant, **12 problèmes critiques** bloquent la mise en production réelle — sécurité, bugs de logique trading, et infrastructure Docker insuffisante.

---

## 1. ARCHITECTURE & DESIGN

### 🔴 ARC-01 — Double codebase sync/async non maintenue en parité
**Fichiers :** `instance.py` (1150L) vs `instance_async.py` (788L), `orchestrator.py` vs `orchestrator_async.py`  
**Problème :** Chaque composant existe en deux versions. Divergences observées :
- `instance.py` : `check_leverage_downgrade()` appelé à chaque tick → `instance_async.py` : déplacé cold path
- `_close_all_positions_market()` : existe SEULEMENT en sync, pas porté en async
- `emergency_stop()` async n'annule pas les ordres ni ne ferme les positions (seulement status change)  
**Impact :** Bug corrigé dans une version absent de l'autre. La version sync est le fallback par défaut (`main.py`).  
**Recommandation :** Déprécier `main.py`. Ne garder que `main_async.py` comme point d'entrée production.

### 🔴 ARC-02 — 8+ singletons globaux sans reset coordonné
**Fichiers :** `persistence.py`, `risk_manager.py`, `order_executor.py`, `stop_loss_manager.py`, `hot_path_optimizer.py`, `cold_path_scheduler.py`  
**Problème :** Les singletons (`_persistence_instance`, `_risk_manager_instance`, `_executor_instance`, etc.) persistent dans le process Python. Restart programmatique sans `reset_*()` hérite de l'état corrompu (circuit breaker déjà à 9/10).  
**Impact :** État fantôme entre redémarrages.  
**Recommandation :** `reset_all_singletons()` appelé dans stop(), ou injection de dépendances.

### 🟡 ARC-03 — max_instances sync=50 vs async=2000
**Fichiers :** `orchestrator.py:119`, `orchestrator_async.py:105`  
**Problème :** L'objectif de 2000 instances n'est atteignable qu'en async. Confusion opérationnelle si `main.py` est lancé.  
**Recommandation :** Guard dans `main.py` avec redirection.

### 🟡 ARC-04 — SPOF : une seule connexion WebSocket pour toutes les paires
**Fichiers :** `websocket_client.py`, `ring_buffer_dispatcher.py`  
**Problème :** 1 connexion WS = si elle tombe, toutes les 2000 instances perdent le flux de prix.  
**Recommandation :** Fallback REST polling pendant la reconnexion WS.

### 🟡 ARC-05 — Absence de mode paper trading explicite
**Fichiers :** `main.py:100`, `signal_handler.py`  
**Problème :** Sans clés API, signaux simplement ignorés. Pas de `PaperOrderExecutor`.  
**Recommandation :** Créer `PaperOrderExecutor` avec slippage réaliste.

### 🟡 ARC-06 — ReconciliationManager reçoit snapshot statique des instances
**Fichier :** `orchestrator.py:247`  
**Problème :** `dict(self._instances)` = copie figée. Instances créées par spin-off non réconciliées.  
**Recommandation :** Passer callback `get_instances()` au lieu de copie.

### 🟢 ARC-07 — Architecture P0-P5 cohérente et bien implémentée
### 🟢 ARC-08 — Circuit breaker avec reset après succès
### 🟢 ARC-09 — Levier X1/X2/X3 avec validation humaine pour X3

---

## 2. CODE QUALITY

### 🔴 CQ-01 — God Object : TradingInstance = 1150 lignes
**Fichier :** `instance.py:76`  
**Problème :** Capital, positions, performance, levier, Kraken mapping, annulation ordres, urgence, recovery SQLite, volatilité, tendance — tout dans une classe.  
**Recommandation :** Extraire `PositionManager`, `PerformanceTracker`, `KrakenSymbolMapper`, `EmergencyHandler`.

### 🟡 CQ-02 — 6 fonctions > 100 lignes
`_close_all_positions_market` (183L), `GridStrategy.on_price` (175L), `BlackSwan.on_price` (138L), `PairsTrading.on_prices` (137L), `GridAsync.on_price` (116L), `SignalHandler._execute_buy` (105L)  
**Recommandation :** Refactorer en sous-fonctions < 50 lignes.

### 🟡 CQ-03 — ~5000 lignes dupliquées sync/async
5 paires de fichiers avec logique métier copiée-collée.  
**Recommandation :** Extraire logique pure, appeler depuis wrappers sync/async.

### 🟡 CQ-04 — Validateur open_position : clés incompatibles entre SignalHandler et Validator
**Fichier :** `validator.py:246` vs `signal_handler.py:91`  
**Problème :** Le validateur attend `balance`/`order_value` mais SignalHandler passe `available_capital`/`signal_price`. Clés mismatch → **validation toujours passante**.  
**Impact :** Aucune validation réelle avant ouverture de position.  
**Recommandation :** Aligner les clés du contexte.

### 🟡 CQ-05 — _execute_sell Grid ferme TOUTES les positions au lieu d'une
**Fichier :** `signal_handler.py:168`  
**Problème :** Quand `level_index is not None`, `positions_to_close = open_positions` (toutes !). Commentaire dit "Fallback" mais c'est le chemin principal Grid.  
**Impact :** Un signal de vente Grid d'un niveau ferme TOUTES les positions.  
**Recommandation :** Mapper level_index → position_id et fermer seulement la bonne.

### 🟡 CQ-06 — TrendStrategy : 20% du capital par trade
**Fichier :** `strategies/trend.py:162`  
**Problème :** 20% par trade. 5 pertes = -67% du capital.  
**Recommandation :** Utiliser `RiskManager.calculate_position_size()` (2% risk/trade).

### 🟢 CQ-07 — Bonne utilisation de `deque(maxlen=)` pour borner la mémoire
### 🟢 CQ-08 — Indicateurs O(1) incrémentaux correctement implémentés
### 🟢 CQ-09 — Thread-safety correcte avec lock/copies hors-lock
### 🟢 CQ-10 — Usage correct de `dataclass(slots=True)`

---

## 3. SÉCURITÉ

### 🔴 SEC-01 — Dashboard sans authentification par défaut
**Fichier :** `api/dashboard.py:22-28`  
**Problème :** Sans `DASHBOARD_API_TOKEN`, tous les endpoints ouverts, y compris `/api/emergency-stop`.  
**Impact :** N'importe qui avec accès réseau peut arrêter le bot.  
**Recommandation :** Token obligatoire si `ENV != development`.

### 🔴 SEC-02 — CORS hardcodé localhost, inutilisable en production
**Fichier :** `api/dashboard.py:65-70`  
**Problème :** Origins `["http://localhost:5173", "http://localhost:3000"]`. Inutilisable sur VPS/Docker.  
**Recommandation :** Variable `CORS_ORIGINS` configurable.

### 🔴 SEC-03 — API keys en attributs publics, sérialisables accidentellement
**Fichiers :** `orchestrator.py:89`, `order_executor.py:57`  
**Problème :** `self.api_key` et `self.api_secret` exposés via `__dict__`, `repr`, serialisation.  
**Recommandation :** `SecretStr` de Pydantic ou chargement depuis env vars à chaque utilisation.

### 🟡 SEC-04 — Validation format IDs absente dans persistence.py
**Problème :** IDs (UUID[:8]) non validés à la lecture. Risque faible (IDs générés internement).  
**Recommandation :** Valider alphanumériques, longueur fixe.

### 🟡 SEC-05 — .env potentiellement commité
**Problème :** `.gitignore` ne contient que 2 lignes, `.env` n'y figure peut-être pas.  
**Recommandation :** Ajouter `.env`, `data/`, `*.db` au `.gitignore`.

### 🟡 SEC-06 — Pas de rate limiting sur le dashboard API
**Recommandation :** Ajouter `slowapi` ou middleware rate limiter.

### 🟢 SEC-07 — Masquage correct des erreurs API dans les logs INFO
### 🟢 SEC-08 — Emergency stop nécessite confirmation "CONFIRM_STOP"

---

## 4. INFRASTRUCTURE

### 🔴 INF-01 — Dockerfile minimal et dangereux
**Fichier :** `Dockerfile`  
**Problème :**
- Pas de `HEALTHCHECK` → Docker/K8s ne sait pas si le bot est healthy
- Run en root (pas de `USER`)
- `.env.example` copié comme `.env` (credentials placeholder en prod)
- Pas de multi-stage build (image grosse avec gcc)
- `CMD` utilise `main.py` (sync) au lieu de `main_async.py`  
**Recommandation :**
```dockerfile
HEALTHCHECK --interval=30s CMD curl -f http://localhost:8080/health || exit 1
RUN adduser --disabled-password --gecos "" appuser
USER appuser
CMD ["python", "-u", "src/autobot/v2/main_async.py"]
```

### 🔴 INF-02 — Pas de docker-compose.yml
**Problème :** Aucun fichier Docker Compose. Le déploiement n'est pas reproductible.  
**Impact :** Configuration manuelle à chaque déploiement, risque d'erreur.  
**Recommandation :** Créer `docker-compose.yml` avec : service autobot, volumes persistants (`data/`), variables d'env, restart policy, logging config.

### 🟡 INF-03 — Pas de monitoring/alerting configuré
**Problème :** Aucun Prometheus metrics, aucun alerting Grafana/PagerDuty. Le `/health` endpoint existe mais n'est pas consommé.  
**Recommandation :** Exporter metrics (positions ouvertes, P&L, latence WS, erreurs API) vers Prometheus. Alertes sur circuit breaker et drawdown critique.

### 🟡 INF-04 — Backup SQLite basique
**Fichier :** `persistence.py:303`  
**Problème :** Backup atomique correct via `sqlite3.backup()`, mais la rotation garde seulement 7 jours et le dossier `data/backups` n'est pas dans un volume Docker.  
**Recommandation :** Volume Docker pour `data/`. Backup vers stockage externe (S3/GCS) en plus.

### 🟡 INF-05 — Variables d'environnement non documentées
**Problème :** Le code utilise `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `DASHBOARD_API_TOKEN`, `DASHBOARD_HOST`, `DASHBOARD_PORT`, `ENV`, `CORS_ORIGINS` (potentiel) — mais `.env.example` n'en liste que 3.  
**Recommandation :** Documenter TOUTES les variables dans `.env.example` avec valeurs par défaut.

### 🟢 INF-06 — WAL mode SQLite activé pour meilleure concurrence
### 🟢 INF-07 — Logging structuré JSON avec rotation (10MB, 5 fichiers)

---

## 5. BUGS POTENTIELS

### 🔴 BUG-01 — Division par zéro dans get_status si initial_capital = 0
**Fichier :** `instance.py:565` et `instance_async.py:338`  
**Code :** `'profit_pct': (self.get_profit() / self._initial_capital * 100)`  
**Problème :** `initial_capital = 0` provoque ZeroDivisionError. Ce cas est réel : `create_instance_auto` crée des instances avec `initial_capital=0` (orchestrator.py:155).  
**Impact :** Crash de l'instance, propagation dans l'orchestrateur.  
**Recommandation :** Guard : `(self.get_profit() / self._initial_capital * 100) if self._initial_capital > 0 else 0.0`. Note : La version async a déjà ce guard, mais la version sync non.

### 🔴 BUG-02 — Race condition dans check_leverage_downgrade (version sync)
**Fichier :** `instance.py:340`  
**Problème :** `check_leverage_downgrade()` lit `_leverage_level` HORS du lock (ligne 340), puis acquiert le lock (ligne 353). Entre les deux, un autre thread peut modifier `_leverage_level`.
```python
def check_leverage_downgrade(self):
    current_level = getattr(self, '_leverage_level', LeverageLevel.X1)  # ← PAS DE LOCK
    if current_level == LeverageLevel.X1:
        return None
    current_dd = self.get_drawdown() * 100  # ← APPEL get_drawdown()    trend = self.detect_trend()                                       # ← APPEL detect_trend()
    with self._lock:                                                   # ← LOCK TARDIF
```
**Impact :** Le levier peut être rétrogradé basé sur un état incohérent.  
**Recommandation :** Acquérir le lock AVANT de lire `_leverage_level`.

### 🔴 BUG-03 — _on_stop_loss_triggered itère les instances SOUS lock global
**Fichier :** `orchestrator.py:266`  
**Problème :** `_on_stop_loss_triggered` acquiert `_instance_lock`, puis itère toutes les instances et appelle `get_positions_snapshot()` et `on_stop_loss_triggered()`. Si `on_stop_loss_triggered` tente d'appeler `close_position`, et que `close_position` appelle `save_state`, et que `save_state` est bloqué sur la persistence SQLite... **deadlock potentiel** si un autre thread tient le lock SQLite et attend le `_instance_lock`.
**Impact :** Bot figé (deadlock).  
**Recommandation :** Copier les instances HORS du lock, puis itérer hors lock (même pattern que le reste du code).

### 🟡 BUG-04 — record_spin_off en async n'est pas thread-safe
**Fichier :** `instance_async.py:250`  
**Problème :** `record_spin_off` est sync et modifie `_current_capital` directement sans lock : `self._current_capital -= amount`. Bien que asyncio soit single-threaded, un `await` entre la lecture et l'écriture (pas dans ce cas simple, mais pattern fragile) pourrait causer une corruption.  
**Recommandation :** Utiliser `async with self._lock` pour cohérence.

### 🟡 BUG-05 — _validate_price rejette variations > 10% = faux positifs en crypto
**Fichier :** `instance_async.py:168`  
**Problème :** `abs(price - self._last_price) / self._last_price > 0.10` rejette le tick. Bitcoin peut varier de >10% en quelques minutes lors d'un flash crash. Ce guard protège contre les bad data mais bloque aussi les vrais mouvements extrêmes.  
**Impact :** Le bot ne trade pas pendant un flash crash — c'est potentiellement voulu, mais empêche aussi les stop-loss logiciels de se déclencher.  
**Recommandation :** Logguer un WARNING et laisser passer après 3 confirmations du même prix (ou vérifier via REST API).

### 🟡 BUG-06 — Timestamps UTC inconsistents
**Fichiers :** `instance.py` utilise `datetime.now(timezone.utc)`, `persistence.py` utilise `datetime.now()` (timezone naive), `validator.py` utilise `datetime.now()`.  
**Problème :** Mélange de timestamps UTC-aware et timezone-naive. La comparaison `trade_time < cutoff` dans `_compute_profit_factor_days` peut échouer silencieusement si `trade.timestamp` est naive et `cutoff` est aware (ou vice versa).  
**Impact :** Calcul incorrect du Profit Factor, décisions de levier/disjoncteur basées sur des données fausses.  
**Recommandation :** Standardiser sur `datetime.now(timezone.utc)` partout.

### 🟡 BUG-07 — get_stop_loss_manager() retourne None si appelé sans order_executor
**Fichier :** `stop_loss_manager.py:199`  
**Problème :** `get_stop_loss_manager()` sans argument retourne `_manager_instance` qui peut être `None`. Le `SignalHandler._execute_buy` (ligne 120) fait `sl_manager = get_stop_loss_manager()` puis `sl_manager.register_stop_loss(...)` → **AttributeError: 'NoneType' has no attribute 'register_stop_loss'**.  
**Impact :** Crash si le stop-loss manager n'a pas été initialisé avant le premier trade.  
**Recommandation :** Guard `if sl_manager:` avant `sl_manager.register_stop_loss()`.

### 🟢 BUG-08 — Positions closed correctement traquées comme "closing" transitoire
### 🟢 BUG-09 — Allocated capital recalculé périodiquement pour corriger la dérive

---

## 6. TESTS

### 🔴 TST-01 — Couverture de test insuffisante sur les fichiers critiques
**Problème :** 14 fichiers de test pour 70+ fichiers source. Aucun test pour :
- `signal_handler.py` (exécution réelle des ordres)
- `signal_handler_async.py`
- `stop_loss_manager.py` / `stop_loss_manager_async.py`
- `reconciliation.py` / `reconciliation_async.py`
- `risk_manager.py`
- `persistence.py`
- `websocket_client.py` / `websocket_async.py`
- `validator.py`
- `strategies/grid.py` (seulement grid_recentering testé)
- `strategies/trend.py`
- `api/dashboard.py`

**Impact :** Les composants les plus critiques (exécution ordres, gestion risques, réconciliation) n'ont AUCUN test.  
**Recommandation :** Priorité absolue : tests unitaires pour `signal_handler.py`, `risk_manager.py`, `persistence.py`, et `validator.py`.

### 🟡 TST-02 — Pas de tests d'intégration end-to-end
**Problème :** Aucun test ne vérifie le flux complet : prix WebSocket → stratégie → signal → validation → exécution → position → P&L.  
**Recommandation :** Créer un test d'intégration avec `PaperOrderExecutor` qui vérifie le flux complet.

### 🟡 TST-03 — Pas de tests de charge
**Problème :** L'objectif est 2000 instances. Aucun test ne vérifie que le système tient sous charge.  
**Recommandation :** Benchmark : créer 2000 instances, injecter 10 ticks/s, mesurer latence P99.

### 🟡 TST-04 — Tests embarqués dans les modules (arbitrage.py, mean_reversion.py)
**Fichiers :** `strategies/arbitrage.py:321`, `strategies/mean_reversion.py:178`  
**Problème :** Tests intégrés dans le code source (fonctions `_run_tests()`). Pas exécutés par pytest, pas dans le dossier `tests/`.  
**Recommandation :** Migrer vers `tests/test_arbitrage.py` et `tests/test_mean_reversion.py`.

### 🟢 TST-05 — Tests existants sont de bonne qualité (ring_buffer, hot_cold_path, order_router)

---

## 7. DOCUMENTATION

### 🟡 DOC-01 — Pas de README.md principal dans le répertoire v2
**Problème :** Aucun `README.md` dans `/src/autobot/v2/`. Le `PLAN_TODO.md` existe mais n'est pas un README. Pas de description de l'architecture, du démarrage, des dépendances.  
**Recommandation :** Créer `README.md` avec : architecture diagram, quickstart, dépendances, configuration.

### 🟡 DOC-02 — Diagramme d'architecture manquant
**Problème :** L'architecture P0-P5 avec ring buffers → async dispatcher → queues → instances est complexe mais non documentée visuellement.  
**Recommandation :** Diagramme Mermaid ou ASCII dans le README.

### 🟢 DOC-03 — Docstrings complètes et de qualité dans les modules critiques
Les fichiers `ring_buffer.py`, `async_dispatcher.py`, `hot_path_optimizer.py`, `cold_path_scheduler.py` ont une documentation exemplaire avec design rationale.

### 🟢 DOC-04 — Tests README bien documenté
Le `tests/README.md` explique clairement comment exécuter les tests Kraken en dry-run.

### 🟢 DOC-05 — Commentaires CORRECTION / CORRECTION CRITIQUE traçables
Le code documente ses corrections avec des tags `CORRECTION Phase N` qui permettent de tracer l'historique des fixes.

---

## PLAN D'ACTION PRIORISÉ

### 🔥 P0 — Bloquants production (faire AVANT tout déploiement)

| # | ID | Action | Effort |
|---|-----|--------|--------|
| 1 | SEC-01 | Rendre DASHBOARD_API_TOKEN obligatoire en prod | 1h |
| 2 | SEC-03 | Protéger API keys (SecretStr ou chargement lazy) | 2h |
| 3 | BUG-01 | Guard division par zéro dans get_status (sync) | 15min |
| 4 | BUG-03 | Fix deadlock _on_stop_loss_triggered (itérer hors lock) | 30min |
| 5 | CQ-05 | Fix _execute_sell Grid : ne fermer que la bonne position | 2h |
| 6 | CQ-04 | Aligner clés validateur open_position | 1h |
| 7 | BUG-07 | Guard NoneType sur get_stop_loss_manager() | 15min |
| 8 | INF-01 | Fix Dockerfile (healthcheck, user, main_async) | 1h |

### 🟠 P1 — Risques élevés (faire dans la semaine)

| # | ID | Action | Effort |
|---|-----|--------|--------|
| 9 | INF-02 | Créer docker-compose.yml | 2h |
| 10 | SEC-02 | CORS configurable via env var | 30min |
| 11 | BUG-02 | Fix race condition check_leverage_downgrade | 30min |
| 12 | BUG-06 | Standardiser timestamps UTC partout | 2h |
| 13 | CQ-06 | TrendStrategy : 2% risk/trade via RiskManager | 1h |
| 14 | ARC-06 | ReconciliationManager : callback au lieu de copie | 1h |
| 15 | TST-01 | Tests pour signal_handler, risk_manager, persistence | 8h |

### 🟡 P2 — Améliorations importantes (dans le mois)

| # | ID | Action | Effort |
|---|-----|--------|--------|
| 16 | ARC-01 | Déprécier version sync, marquer main.py DEPRECATED | 2h |
| 17 | ARC-02 | Implémenter reset_all_singletons() | 3h |
| 18 | CQ-01 | Refactorer TradingInstance en sous-classes | 8h |
| 19 | CQ-03 | Extraire logique pure des doublons sync/async | 16h |
| 20 | ARC-05 | Créer PaperOrderExecutor | 4h |
| 21 | INF-03 | Ajouter Prometheus metrics | 4h |
| 22 | TST-02 | Tests d'intégration end-to-end | 8h |
| 23 | DOC-01 | README.md avec architecture diagram | 3h |

---

## POINTS FORTS DU PROJET ✅

1. **Architecture hot/cold path** (P4) — GC désactivé sur le hot path, ring buffer SPMC lock-free ~200-400ns/write
2. **Crash recovery** — SQLite WAL + positions restaurées au redémarrage
3. **Circuit breaker** — 10 erreurs API consécutives → arrêt d'urgence automatique
4. **Réconciliation Kraken** — Détection des divergences état local vs exchange
5. **Ring buffer SPMC** — O(1) write, O(1) read, zero-copy, pre-allocated
6. **AsyncDispatcher** — O(N_pairs) tasks au lieu de O(N_instances), excellent pour 2000 instances
7. **Levier à 3 paliers** — Garde-fous stricts avec validation humaine pour X3
8. **OS tuning** — TCP_NODELAY, SO_BUSY_POLL, CPU pinning, SCHED_FIFO
9. **Indicateurs O(1)** — RollingEMA, RollingRSI incrémentaux sans recalcul
10. **Grid recentering** — Auto-adaptation quand le prix dérive > 5%

---

*Fin de l'audit. Les 12 items P0 doivent être résolus avant tout déploiement en production réelle avec capital réel.*
