## MISSION: Corrections Sécurité & Architecture — CRITIQUES + WARNINGS

### Contexte
11 problèmes critiques + 23 warnings à corriger avant production.

---

## 🔴 CRITIQUES (11)

### ROB-01 — Write-Ahead Log pour ordres (LE PLUS CRITIQUE)
**Fichier:** src/autobot/v2/signal_handler.py, order_executor_async.py
**Problème:** Pas de WAL → double achat possible après crash
**Correction:**
1. Créer `order_wal.py` — Write-Ahead Log SQLite pour intentions d'ordres
2. Avant chaque ordre Kraken: écrire dans WAL (status=PENDING)
3. Après confirmation Kraken: update WAL (status=EXECUTED)
4. Au démarrage: vérifier ordres PENDING et réconcilier

### SEC-02 — Dashboard HTTPS
**Fichier:** src/autobot/v2/api/dashboard.py
**Correction:**
- Ajouter support TLS (certificat auto-signé ou Let's Encrypt)
- Flag `--ssl` ou variable `DASHBOARD_USE_SSL=true`
- HSTS headers

### ARCH-01 — asyncio.Lock sur _instances
**Fichier:** src/autobot/v2/orchestrator_async.py
**Correction:**
```python
self._instances_lock = asyncio.Lock()
# Utiliser dans create_instance, remove_instance, get_instance
```

### ROB-02 — Stop-loss orphelins
**Fichier:** src/autobot/v2/signal_handler.py
**Correction:**
- Retry avec backoff sur cancel_order
- Vérifier périodiquement stop-loss actifs vs positions ouvertes
- Ne pas fermer position localement avant confirmation annulation SL

### SEC-03 — Nonce monotone
**Fichier:** src/autobot/v2/order_executor_async.py
**Correction:**
```python
_nonce_counter = int(time.time() * 1000)
_nonce_lock = asyncio.Lock()

async def _get_nonce(self):
    async with self._nonce_lock:
        self._nonce_counter += 1
        return str(self._nonce_counter)
```

### SEC-01 — Masquer API secrets
**Fichiers:** orchestrator.py, orchestrator_async.py
**Correction:**
- `__repr__` qui masque `api_secret`
- Ne pas logger les secrets
- `SecretStr` pattern

### ARCH-02 — Vérification ressources avant création instance
**Fichier:** src/autobot/v2/orchestrator_async.py
**Correction:**
- Vérifier RAM disponible avant création
- Réduire max_instances dynamiquement si ressources basses

### ARCH-03 — Pool connexions SQLite
**Fichier:** src/autobot/v2/persistence.py
**Correction:**
- Connexion persistante au lieu de `sqlite3.connect()` à chaque appel
- Ou utiliser `aiosqlite` pour async

### SEC-04 — sys.path sécurisé
**Fichier:** src/autobot/v2/main_async.py
**Correction:**
- Vérifier que le chemin pointe vers un répertoire attendu
- Ou utiliser `sys.path.append()` au lieu de `insert(0, ...)`

### SEC-05 — sysctl_config.sh warnings
**Fichier:** src/autobot/v2/sysctl_config.sh
**Correction:**
- Double confirmation avant persistence
- Documentation des risques
- Flag `--dry-run` pour preview

### PROD-01 — Health check
**Fichier:** src/autobot/v2/main_async.py
**Correction:**
- Endpoint `/health` avec status système
- RAM, CPU, connections, dernière tick reçue

---

## 🟡 WARNINGS Importants (Top 10)

### SEC-06 — CORS restreint en prod
**Fichier:** dashboard.py
**Correction:** Origins configurables via env var

### SEC-07 — Auth bypass log ERROR
**Fichier:** dashboard.py  
**Correction:** Log ERROR visible si auth désactivée

### SEC-08 — Whitelist méthodes API enum
**Fichier:** order_executor.py
**Correction:** Enum strict au lieu de if/elif chain

### SEC-09 — Stack traces masquées en prod
**Fichiers:** Multiple
**Correction:** `logger.exception()` uniquement en DEBUG en prod

### SEC-10 — Timeouts krakenex configurables
**Fichier:** orchestrator.py
**Correction:** `KRAKEN_TIMEOUT` env var

### SEC-11 — SQLite isolation level
**Fichier:** persistence.py
**Correction:** `isolation_level='EXCLUSIVE'` sur transactions critiques

### SEC-12 — validate before insert/update
**Fichier:** persistence.py
**Correction:** Validation types avant DB

### SEC-13 — Log injection
**Fichiers:** Multiple
**Correction:** Échapper les données utilisateur dans les logs

### ARCH-04 — Timeout coroutines
**Fichier:** websocket_async.py
**Correction:** `asyncio.timeout()` sur les awaits

### ARCH-05 — Bounded queues
**Fichier:** order_router.py
**Correction:** Maxsize sur les queues avec politique de drop

---

## Livrables
1. Tous les fichiers corrigés
2. Tests mis à jour et passants
3. Documentation des changements
