# 🔒 REVIEW SÉCURITÉ COMPLÈTE P0-P6 — AutoBot V2

**Reviewé par:** Claude Opus 4.6  
**Date:** 2026-04-02  
**Scope:** P0 (asyncio migration) → P6 (speculative execution)  
**Fichiers analysés:** 10 fichiers cœur + orchestrator + main + websocket + executor  

---

## 📊 RÉSUMÉ EXÉCUTIF

| Sévérité | Count | Status |
|----------|-------|--------|
| 🔴 CRITIQUE | 6 | Action immédiate requise |
| 🟡 WARNING | 9 | À corriger avant production |
| 🟢 INFO | 7 | Améliorations recommandées |

**Score global: 6.5/10** — Architecture solide mais failles de sécurité financière critiques.

---

## 🔴 CRITIQUES — Action Immédiate (Priorité 1-3)

### 🔴 C1 — Division par zéro sur le hot path (P6: speculative_order_cache + order_router)
**Priorité: 1/10 (MAX)**  
**Fichier:** `order_router.py:263`, `fast_order_builder.py:158`  
**Impact:** Crash du processus entier, perte potentielle d'ordres en file

```python
# order_router.py — submit_speculative()
volume = template.capital_per_level / live_price  # 💥 Si live_price == 0.0

# fast_order_builder.py — _compute_volume()
return template.capital_per_level / live_price    # 💥 Même problème
```

**Scénario:** Un tick WebSocket avec `price=0.0` (donnée corrompue, flash crash, ou parsing JSON erroné) provoque une `ZeroDivisionError` non catchée. Comme `on_price_update()` est le hot path (P4: aucun try/except), l'exception **remonte et tue la task consumer**, rendant l'instance muette.

**Correction:**
```python
if live_price <= 0:
    logger.error("❌ live_price <= 0, ordre ignoré: %s %s", symbol, side)
    return OrderResult(success=False, error="Invalid price")
```

---

### 🔴 C2 — API Keys en mémoire sans protection
**Priorité: 1/10**  
**Fichiers:** `order_executor_async.py:62-63`, `order_router.py:177-178`, `orchestrator_async.py:50`  
**Impact:** Fuite de clés API en cas de dump mémoire, core dump, ou exception non catchée loggée

```python
self.api_key = api_key          # Plain text en attribut d'instance
self.api_secret = api_secret    # HMAC secret en clair
```

**Problèmes:**
1. `api_secret` reste en mémoire Python pendant toute la durée de vie du processus
2. Un `repr()` accidentel ou un logging d'exception peut exposer les clés
3. Aucune vérification que les clés sont des chaînes non-vides avant usage
4. `os.getenv("KRAKEN_API_SECRET")` dans `main_async.py` — le secret persiste dans `os.environ`

**Correction:**
- Utiliser un objet `SecretStr` qui masque `__repr__` et `__str__`
- Zéroiser le secret dès que la session HMAC est configurée
- Ne jamais logger les objets contenant des credentials

---

### 🔴 C3 — Race condition dans le singleton OrderRouter
**Priorité: 2/10**  
**Fichier:** `order_router.py:461-467`  

```python
_router_lock = asyncio.Lock()  # ← Créé au niveau du MODULE

async def get_order_router(...) -> OrderRouter:
    global _router_instance
    async with _router_lock:     # ← Deadlock si appelé avant event loop
        if _router_instance is None:
            _router_instance = OrderRouter(api_key, api_secret)
    return _router_instance
```

**Problème:** `asyncio.Lock()` est créé à l'import du module, AVANT qu'un event loop existe. En Python 3.10+, `asyncio.Lock()` s'attache à l'event loop courant à la création. Si le module est importé avant `asyncio.run()`, le Lock est lié à un loop inexistant → `RuntimeError: attached to a different event loop`.

**Même problème dans:**
- `order_executor_async.py` — singleton `_executor_instance`
- `hot_path_optimizer.py` — singleton `_singleton`
- `cold_path_scheduler.py` — singleton `_singleton`

**Correction:** Créer le Lock de façon lazy, ou utiliser un pattern singleton sans Lock (Python asyncio est single-threaded).

---

### 🔴 C4 — Nonce Kraken basé sur `time.time()` — rejeu possible
**Priorité: 2/10**  
**Fichier:** `order_executor_async.py:114`

```python
params["nonce"] = str(int(time.time() * 1000))
```

**Problème:** `time.time()` a une résolution de ~1ms. Si deux appels API sont faits dans la même milliseconde (très probable à haute fréquence), le nonce est identique → Kraken rejette avec "Invalid nonce". Pire: un nonce **réutilisé** avec des paramètres différents constitue un vecteur de replay attack.

**Correction:**
```python
# Nonce monotonique garanti unique
_nonce_counter = itertools.count(int(time.time() * 1000))
params["nonce"] = str(next(_nonce_counter))
```

---

### 🔴 C5 — Pas de validation des données WebSocket entrantes
**Priorité: 2/10**  
**Fichier:** `websocket_async.py:154-162`

```python
async def _process_ticker(self, pair: str, data: dict) -> None:
    try:
        price = float(data.get("c", [0])[0])   # ← 0 par défaut si absent!
        bid = float(data.get("b", [0])[0])
        ask = float(data.get("a", [0])[0])
        volume = float(data.get("v", [0, 0])[1])
    except (IndexError, TypeError, ValueError):
        return
```

**Problèmes:**
1. `price=0.0` est accepté et propagé → déclenche C1 (division par zéro)
2. `bid > ask` (données invalides/manipulation) n'est pas détecté
3. `price` négatif passe sans vérification
4. Un `bid=0, ask=0, price=0` crée un `TickerData` valide qui se propage dans TOUT le pipeline
5. Pas de sanity check sur la cohérence `bid ≤ price ≤ ask`
6. `volume` peut être NaN (float("nan") passe float())

**Impact:** Données corrompues propagées à 2000 instances → ordres erronés, divisions par zéro, calculs de PnL faux.

**Correction:**
```python
if price <= 0 or bid <= 0 or ask <= 0 or bid > ask:
    logger.warning("⚠️ Ticker invalide %s: p=%.2f b=%.2f a=%.2f", pair, price, bid, ask)
    return
if math.isnan(price) or math.isinf(price):
    return
```

---

### 🔴 C6 — `_write_volume_to_buf` overflow sur volumes extrêmes
**Priorité: 3/10**  
**Fichier:** `fast_order_builder.py:55-90`

```python
_VOL_BUF_SIZE = 32     # max decimal string
_BODY_BUF_SIZE = 256

def _write_volume_to_buf(buf: bytearray, offset: int, volume: float) -> int:
    scaled = int(volume * _SCALE + 0.5)   # ← Overflow si volume > 92233720368.0
    int_part = scaled // _SCALE            # ← int_part peut avoir >24 digits
```

**Problème:** Si `volume` est anormalement grand (bug en amont, données corrompues, division par un prix proche de zéro), `_write_volume_to_buf` écrit au-delà de la taille du buffer → `IndexError` ou corruption silencieuse du bytearray.

Par exemple: `capital_per_level=50.0, live_price=0.001` → `volume=50000.0` → 14 chars OK.  
Mais `live_price=0.000001` → `volume=50000000.0` → potentiellement OK mais limite.

**Correction:** Ajouter un bounds check et/ou un `assert offset < len(buf)` en debug.

---

## 🟡 WARNINGS — Corriger Avant Production (Priorité 4-6)

### 🟡 W1 — OrderRouter `_process_loop` — future.set_result après annulation
**Priorité: 4/10**  
**Fichier:** `order_router.py:335`

```python
if not request.future.done():
    request.future.set_result(result)
```

**Problème:** Entre le check `not request.future.done()` et `set_result()`, il n'y a pas de risque en asyncio single-thread MAIS si le caller a `await asyncio.wait_for(request.future, timeout=...)` et que le timeout expire, la future est annulée. Le `set_result` sur une future annulée lance `asyncio.InvalidStateError`.

Le check `not request.future.done()` est correct et protège contre ça, MAIS la race window existe si un timeout asyncio annule la future entre les deux lignes. En CPython single-thread asyncio, ce n'est pas possible (pas de preemption), mais c'est fragile.

**Correction:** Wrapper dans un try/except:
```python
try:
    request.future.set_result(result)
except asyncio.InvalidStateError:
    logger.debug("Future already done for %s", request.order_type)
```

---

### 🟡 W2 — RingBuffer pas thread-safe — documentation dit "safe" mais c'est faux hors asyncio
**Priorité: 4/10**  
**Fichier:** `ring_buffer.py:24-30`

La documentation dit "CPython GIL ensures atomic" mais:
1. `ring_buffer.py` est un module Python pur — si importé par un code multi-thread (ex: test runner, Flask endpoint), les garanties tombent
2. PyPy, GraalPy, et le futur free-threaded CPython (PEP 703) ne garantissent PAS l'atomicité des stores de référence
3. Le `_write_seq` increment (`seq + 1`) est atomic sous GIL mais PAS sous no-GIL

**Impact:** Corruption de données si le code est réutilisé hors asyncio single-thread.

**Correction:**
```python
import warnings
class RingBuffer:
    def __init__(self, ...):
        if not _is_cpython_with_gil():
            warnings.warn("RingBuffer requires CPython with GIL", RuntimeWarning)
```

---

### 🟡 W3 — HotPathOptimizer désactive le GC globalement — fuite mémoire possible
**Priorité: 4/10**  
**Fichier:** `hot_path_optimizer.py:65-72`, `orchestrator_async.py:236-237`

```python
def enter_hot_path(self) -> None:
    gc.disable()   # ← Désactive le GC pour TOUT le processus

# orchestrator_async.py
self.hot_optimizer.enter_hot_path()   # Au démarrage
self.cold_scheduler.schedule_gc(self.hot_optimizer, interval=30.0)  # GC toutes les 30s
```

**Problème:**
1. `gc.collect()` tous les 30s est insuffisant si le taux d'allocation est élevé (2000 instances × 10 ticks/s = 20 000 TickerData/s)
2. Les cycles de références (ex: instance → strategy → instance) ne sont JAMAIS collectés entre deux `force_gc()` → buildup de 30s de garbage
3. Si `force_gc()` prend >100ms (beaucoup d'objets), c'est un stall observable sur le event loop
4. Si le `ColdPathScheduler` crashe silencieusement, le GC n'est JAMAIS relancé → OOM

**Correction:**
- Monitorer la durée de `gc.collect()` et ajuster l'interval dynamiquement
- Ajouter un failsafe: si `force_gc()` n'a pas été appelé depuis 2 minutes, le hot path optimizer le force automatiquement

---

### 🟡 W4 — ColdPathScheduler `_run_oneshot` avale les exceptions
**Priorité: 4/10**  
**Fichier:** `cold_path_scheduler.py:122-127`

```python
async def _run_oneshot(self, coro: Awaitable[Any]) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        self._errors += 1
        logger.error("❄️ Cold-path task error: %s", exc, exc_info=True)
```

**Problème:** Si `save_state()` échoue systématiquement (ex: disque plein, SQLite corrupt), l'erreur est loggée mais **aucune alerte n'est levée**. Le bot continue à trader sans persistance → en cas de crash, TOUTES les positions sont perdues.

**Correction:**
- Ajouter un seuil d'erreurs consécutives (circuit breaker pour la persistance)
- Notifier via callback si les erreurs cold-path dépassent un seuil

---

### 🟡 W5 — Pas de TLS certificate pinning sur le WebSocket Kraken
**Priorité: 5/10**  
**Fichier:** `websocket_async.py:90-96`

```python
self._ws = await websockets.connect(
    self.WS_PUBLIC,               # wss://ws.kraken.com
    ping_interval=30,
    ping_timeout=10,
    close_timeout=5,
)
```

**Problème:** Aucun `ssl_context` custom n'est passé. La connexion TLS utilise les CA par défaut du système. Un attaquant en position MITM (DNS spoofing, compromission du réseau) peut intercepter le flux de prix et envoyer de faux tickers → le bot prend des décisions de trading sur des données manipulées.

**Correction:**
```python
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = True
ctx.verify_mode = ssl.CERT_REQUIRED
# Optionnel: pin le certificat Kraken
self._ws = await websockets.connect(self.WS_PUBLIC, ssl=ctx, ...)
```

---

### 🟡 W6 — `_safe_api_call` retry sans idempotency check
**Priorité: 5/10**  
**Fichier:** `order_executor_async.py:127-167`

```python
async def _safe_api_call(self, method: str, max_retries: int = 3, **params) -> ...:
    for attempt in range(max_retries):
        # ...
        response = await self._query_private(method, **params)
        if response.get("error"):
            if "Rate limit exceeded" in error_msg:
                await asyncio.sleep(2 ** attempt)
                continue    # ← RETRY l'AddOrder!
```

**Problème:** `AddOrder` n'est PAS idempotent. Si Kraken reçoit l'ordre, l'exécute, mais la réponse est perdue (timeout réseau), le retry **soumet un DEUXIÈME ordre identique**. Avec 3 retries, on peut avoir 3x le volume intentionnel.

**Impact:** Double/triple exécution d'ordres = perte financière directe.

**Correction:**
- Utiliser `userref` unique par ordre pour détecter les doublons
- Sur rate limit pour `AddOrder`, ne PAS retry automatiquement — remettre en queue
- Distinguer les erreurs idempotentes (QueryOrders, Balance) des non-idempotentes (AddOrder)

---

### 🟡 W7 — InstanceQueue `put_nowait_drop_oldest` TOCTOU
**Priorité: 5/10**  
**Fichier:** `instance_queue.py:117-139`

```python
def put_nowait_drop_oldest(self, data: Any) -> bool:
    if self._queue.full():
        try:
            self._queue.get_nowait()   # ← (1) Retire l'ancien
        except asyncio.QueueEmpty:
            pass
    try:
        self._queue.put_nowait(data)   # ← (2) Ajoute le nouveau
    except asyncio.QueueFull:          # ← TOCTOU: queue re-remplie entre (1) et (2)
        pass                           # ← TICK PERDU SILENCIEUSEMENT
```

**Problème:** En théorie, dans single-thread asyncio, pas de preemption entre (1) et (2). MAIS le commentaire dans le code reconnaît la race ("Extremely rare: consumer emptied + refilled..."). C'est un signe que la logique n'est pas atomique de façon prouvable.

**Impact réel:** Faible en asyncio single-thread, mais un tick est silencieusement perdu sans comptabilisation (le `pass` ne met pas à jour les compteurs).

**Correction:** Au minimum, incrémenter `_drop_count` dans le catch `QueueFull`.

---

### 🟡 W8 — Singleton pattern avec état global mutable — testabilité cassée
**Priorité: 5/10**  
**Fichiers:** Tous les fichiers avec `_singleton` pattern

```python
# hot_path_optimizer.py, cold_path_scheduler.py, order_router.py, order_executor_async.py
_singleton = None
def get_xxx():
    global _singleton
    if _singleton is None:
        _singleton = Xxx()
    return _singleton
```

**Problème:**
1. Tests parallèles partagent l'état → tests flaky
2. `reset_order_router()` existe mais `reset_hot_path_optimizer()` non
3. `gc.disable()` via le singleton HotPathOptimizer affecte tous les tests suivants
4. Le `OrderRouter` singleton garde une référence à l'`OrderExecutorAsync` singleton → pas de mock possible sans monkey-patching

**Correction:** Utiliser dependency injection (passer les objets via constructeur) plutôt que des singletons globaux.

---

### 🟡 W9 — `submit_speculative` fallback envoie `live_price` comme `volume`
**Priorité: 6/10**  
**Fichier:** `order_router.py:287-293`

```python
# --- cache MISS: standard construction ---
order = {
    "type": "market",
    "symbol": symbol,
    "side": side,
    "volume": live_price,  # caller expected to provide volume; use live_price as hint
}
```

**Problème:** Le commentaire dit "caller expected to provide volume; use live_price as hint" mais `live_price` est le PRIX du marché (ex: 48500.0 pour BTC). Si ce dict est envoyé à Kraken, on essaie d'acheter **48500 BTC** au lieu du volume désiré. Le commentaire montre que le développeur était conscient du problème mais n'a pas implémenté le fallback correctement.

**Impact:** Ordre rejeté par Kraken (volume insuffisant) dans le meilleur cas. Dans le pire cas, exécution partielle massive.

**Correction:** Le fallback doit recalculer le volume correctement:
```python
volume = capital_per_level / live_price if live_price > 0 else 0
```

---

## 🟢 INFO — Améliorations Recommandées (Priorité 7-10)

### 🟢 I1 — Logging verbeux sur le hot path
**Priorité: 7/10**  
**Fichier:** `ring_buffer_dispatcher.py:148`, `async_dispatcher.py:200`

Le `logger.warning()` dans les boucles de dispatch peut créer de la contention (string formatting + I/O) sous charge. Même si le warning est throttled (warn every N), la formation du string se fait à chaque appel si le logger est enabled.

**Correction:** Utiliser `logger.isEnabledFor(logging.WARNING)` guard, ou un compteur modulo.

---

### 🟢 I2 — `_price_history` deque non bornée en pratique
**Priorité: 7/10**  
**Fichier:** `instance_async.py:70-71`

```python
self._max_history_size = 1000
self._price_history: deque = deque(maxlen=self._max_history_size)
```

C'est borné à 1000 éléments par instance. Avec 2000 instances: 2M tuples `(timestamp, price)` en mémoire. Chaque tuple = ~72 bytes → ~144 MB. Acceptable mais à surveiller.

**Pas de problème immédiat, mais:**
- `detect_trend()` et `get_volatility()` itèrent sur toute la deque → O(1000) par appel
- Ces méthodes sont appelées dans `_main_loop` qui itère sur toutes les instances → O(2000 × 1000) = O(2M) par cycle

---

### 🟢 I3 — Pas de health check endpoint
**Priorité: 7/10**  
**Fichier:** `main_async.py`

Le bot n'expose aucun endpoint HTTP de santé. En production, impossible de monitorer:
- Le lag du ring buffer
- Le nombre de drops
- L'état du rate limiter
- Le nombre d'erreurs cold-path
- L'uptime du GC

**Correction:** Ajouter un endpoint `/health` (aiohttp simple) qui expose `orchestrator.get_status()`.

---

### 🟢 I4 — `on_price_update` n'a aucun try/except
**Priorité: 7/10**  
**Fichier:** `instance_async.py:292-311`

```python
async def on_price_update(self, data: TickerData) -> None:
    opt = self._hot_optimizer
    t0 = opt.start_tick() if opt is not None else 0
    self._last_price = data.price
    self._price_history.append((data.timestamp, data.price))
    if self._strategy is not None and self.status == InstanceStatus.RUNNING:
        self._strategy.on_price(data.price)   # ← Si on_price() raise, la task meurt
    if opt is not None:
        opt.record_tick(t0)
```

**Note:** Le `_queue_consumer_loop` catch les exceptions de `on_price_update` (ligne 242), donc l'instance ne meurt PAS. C'est correctement implémenté au niveau du consumer. Cependant, si `opt.record_tick(t0)` n'est jamais appelé après une exception dans `on_price`, les stats de latence sont biaisées.

---

### 🟢 I5 — WebSocket reconnection ne limite pas les tentatives
**Priorité: 8/10**  
**Fichier:** `websocket_async.py:202-237`

```python
async def _reconnect(self) -> None:
    # ...
    self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_reconnect_backoff)
```

Le backoff est capé à 60s, mais il n'y a **aucune limite** sur le nombre total de reconnexions. Si Kraken est down pendant des heures, le bot tente de se reconnecter toutes les 60s indéfiniment, consommant des ressources et polluant les logs.

---

### 🟢 I6 — `_check_global_health` crée un `RiskManager` à chaque appel
**Priorité: 8/10**  
**Fichier:** `orchestrator_async.py:204-208`

```python
async def _check_global_health(self) -> None:
    # ...
    rm = get_risk_manager()
    rm.set_orchestrator(self)
    rm.check_global_risk(active)
```

`set_orchestrator(self)` est appelé dans la boucle de health check. Si `RiskManager` est un singleton, il est réassigné à chaque itération. Si une autre référence au `RiskManager` est utilisée en parallèle, l'orchestrateur peut être swappé de façon inattendue.

---

### 🟢 I7 — Signal handlers dans `main_async.py` — lambda crée une closure fragile
**Priorité: 9/10**  
**Fichier:** `main_async.py:90`

```python
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
```

Ce lambda capture `self` par closure. Si `stop()` lève une exception, la task n'est pas attendue (fire-and-forget) → l'exception est ignorée et le processus peut ne pas s'arrêter proprement.

---

## 📋 RÉPONSES AUX QUESTIONS SPÉCIFIQUES

### Q1: Failles de sécurité dans l'architecture async?
**OUI — 3 failles majeures:**
1. **API keys en clair** (C2) — Compromission mémoire = full account takeover
2. **Nonce time-based** (C4) — Replay attack possible
3. **Pas de TLS pinning** (W5) — MITM sur les prix possible

### Q2: Locks correctement gérés?
**Partiellement:**
- ✅ `asyncio.Lock` utilisé correctement dans `instance_async.py` pour les mutations de capital
- ✅ `AsyncRateLimiter` utilise `async with self._lock` systématiquement
- ❌ Le RingBuffer n'a aucun lock (voulu, mais fragile hors CPython GIL) (W2)
- ❌ Les singletons modules-level avec `asyncio.Lock` peuvent deadlock (C3)
- ⚠️ `on_price_update` est volontairement lock-free (P4) — correct en asyncio single-thread mais non prouvé formellement

### Q3: Race conditions entre RingBuffer et OrderRouter?
**Non directement**, mais:
- Le RingBuffer et l'OrderRouter n'interagissent pas directement
- Le chemin est: RingBuffer → AsyncDispatcher → InstanceQueue → on_price_update → strategy → OrderRouter
- ⚠️ Si deux instances soumettent un ordre EMERGENCY simultanément, le PriorityQueue les traite en séquence (correct)
- ⚠️ Le `_process_loop` de l'OrderRouter est single-threaded — pas de race condition interne

### Q4: Le hot path est-il vraiment isolé du cold path?
**OUI, bien fait:**
- ✅ `on_price_update` n'a aucun `await`, aucun Lock, aucune I/O
- ✅ `check_leverage_downgrade` déplacé dans `ColdPathScheduler` (60s periodic)
- ✅ Persistence via `run_in_executor` (thread pool)
- ✅ GC désactivé sur le hot path, collecté périodiquement
- ⚠️ Seul bémol: `_strategy.on_price()` est appelé de façon synchrone — si une stratégie est lente, elle bloque le tick processing pour CETTE instance

### Q5: Fuites mémoire possibles?
**OUI, risque modéré:**
1. GC désactivé 30s entre les collections (W3) — les cycles s'accumulent
2. `_oneshot_tasks` dans ColdPathScheduler: pruné à 256 mais les tasks complétées restent jusqu'au seuil
3. `_trades` deque bornée à 1000 → OK
4. `_price_history` deque bornée à 1000 → OK
5. `_call_times` et `_order_times` dans AsyncRateLimiter: purgés par `_purge_old_calls/orders` mais seulement quand `can_execute`/`wait_time`/`get_status` sont appelés → entre les purges, les listes croissent linéairement

### Q6: Gestion des erreurs robuste?
**Inégale:**
- ✅ Circuit breaker dans `OrderExecutorAsync` (10 erreurs consécutives)
- ✅ Exponential backoff sur rate limits
- ✅ `_queue_consumer_loop` catch les exceptions et continue
- ❌ `_process_ticker` accepte des données invalides (C5)
- ❌ Division par zéro non protégée (C1)
- ❌ Cold-path errors avalées silencieusement (W4)
- ❌ Retry aveugle sur `AddOrder` (W6) — duplication d'ordres

---

## 🎯 PLAN D'ACTION PRIORISÉ

### Phase 1 — Immédiat (avant tout trade réel)
| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| C1 | Guard `live_price <= 0` dans order_router + fast_order_builder | 15 min | Prévient crash |
| C5 | Validation prix WebSocket (>0, !NaN, bid≤ask) | 30 min | Prévient propagation données corrompues |
| C4 | Nonce monotonique (compteur atomique) | 15 min | Prévient replay attack |
| W9 | Fix fallback `submit_speculative` (volume ≠ prix) | 10 min | Prévient ordre catastrophique |
| W6 | Skip retry pour AddOrder (non-idempotent) | 30 min | Prévient double exécution |

### Phase 2 — Avant production (1-2 jours)
| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| C2 | SecretStr pour API keys + purge mémoire | 2h | Sécurité credentials |
| C3 | Fix singletons asyncio.Lock (lazy init) | 1h | Prévient deadlock module import |
| C6 | Bounds check dans _write_volume_to_buf | 30 min | Prévient buffer overflow |
| W1 | Try/except InvalidStateError sur future.set_result | 10 min | Robustesse |
| W4 | Circuit breaker sur erreurs cold-path persistance | 1h | Détecte perte de persistance |
| W5 | SSL context avec verify sur WebSocket | 30 min | Prévient MITM |

### Phase 3 — Hardening (1 semaine)
| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| W2 | Warning runtime si non-CPython/no-GIL | 30 min | Future-proofing |
| W3 | GC adaptatif + failsafe OOM | 2h | Prévient fuite mémoire |
| W7 | Fix TOCTOU dans InstanceQueue + compteur | 15 min | Observabilité |
| W8 | Dependency injection remplaçant singletons | 4h | Testabilité |
| I3 | Endpoint /health HTTP | 2h | Monitoring |

---

## 🏗️ RÉSUMÉ ARCHITECTURAL

### Points Forts
1. **Architecture en couches claire:** WS → RingBuffer → Dispatcher → Queue → Instance
2. **Hot/Cold separation effective:** P4 implémenté correctement, GC-free hot path
3. **Backpressure bien gérée:** Drop-oldest policy cohérente à chaque niveau
4. **Performance mesurée:** P99 1.08µs documenté avec preuves (test_hot_cold_path)
5. **Circuit breaker API:** Protection contre cascade d'erreurs
6. **Tests exhaustifs:** 253 tests couvrent les chemins critiques

### Points Faibles
1. **Validation des entrées quasi-inexistante** — le pipeline fait confiance aux données WS
2. **Sécurité financière fragile** — division par zéro, double exécution, volume=prix
3. **Credentials management basique** — plain text en mémoire
4. **Singletons omniprésents** — état global mutable, test-hostile
5. **Monitoring absent** — pas d'endpoint health, pas d'alerting structuré

---

*Review terminée. Les 6 critiques doivent être résolues avant tout déploiement en production avec des fonds réels.*