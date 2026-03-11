# 🔒 REVIEW SÉCURITÉ FINALE — AUTOBOT V2
## Post 4 phases de corrections | 11 mars 2026

---

## 📋 RÉSUMÉ EXÉCUTIF

| Catégorie | Critiques | Majeurs | Mineurs |
|-----------|:-:|:-:|:-:|
| Sécurité Exchange | 0 | 2 | 3 |
| Sécurité Financière | 1 | 3 | 2 |
| Race Conditions / Deadlocks | 0 | 1 | 1 |
| Crash Scenarios | 0 | 2 | 2 |
| Données / Fuites | 0 | 1 | 1 |
| **TOTAL** | **1** | **9** | **9** |

**Fichiers analysés :** 14 fichiers Python, ~3 200 lignes de code

---

## 1. 🔑 SÉCURITÉ EXCHANGE

### 1.1 OrderExecutor — Clés API, logs, exceptions

**✅ Bien fait :**
- Lazy init client Kraken, clés vérifiées à l'usage
- Rate limiting 1s minimum entre appels
- Retry + backoff exponentiel (3 tentatives)
- Singleton thread-safe (`_executor_lock`)
- Logging sécurisé (clés jamais loguées)

**⚠️ Risques :**

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| E1 | **Clés API plaintext en RAM** — core dump les expose | Faible | Mineur | **Partielle** — OK paper trading. Prod: vault/keyring |
| E2 | **`_safe_api_call` whitelist incomplète** — Seules `AddOrder`, `CancelOrder`, `QueryOrders`, `OpenOrders` sont routées. Or `get_closed_orders()` → `ClosedOrders`, `get_balance()` → `Balance`, `get_trade_balance()` → `TradeBalance`. **Ces 3 méthodes retournent `{error: "Méthode inconnue"}`.** La réconciliation et le check balance sont **cassés**. | **Haute** | **Majeur** | **Insuffisante** ⛔ |
| E3 | **Pas de validation structure réponse Kraken** — Suppose `response['result']['txid']` est une liste | Moyenne | Mineur | **Partielle** — try/except rattrape |
| E4 | **`Instance._cancel_all_orders` crée son propre client krakenex** au lieu d'utiliser OrderExecutor. Bypass rate limiting, duplication. | Moyenne | Mineur | **Partielle** — Fonctionne mais anti-pattern |

### 1.2 SignalHandler — Validation, circuit breakers

**✅ Bien fait :**
- Cooldown 5s entre signaux
- Validation volume > 0
- Stop-loss posé sur Kraken AVANT position locale
- Annulation SL avant vente (anti double-sell)

**⚠️ Risques :**

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| E5 | **ValidatorEngine VIDE** — `self.validator = ValidatorEngine()` sans aucun validateur enregistré. `validate('open_position', context)` itère sur liste vide → toujours `GREEN`. **La validation pré-trade est un no-op.** Devrait utiliser `create_default_validator_engine()`. | **Haute** | **Majeur** | **Insuffisante** ⛔ |
| E6 | **Pas de circuit breaker** — Si Kraken renvoie 50 erreurs d'affilée, le bot continue. Rate limiting ≠ circuit breaker. Devrait trigger `emergency_stop()` après N échecs consécutifs. | Moyenne | Majeur | **Insuffisante** |

### 1.3 StopLossManager — Permissions, accès ordres

**✅ Bien fait :**
- Stop-loss gérés PAR Kraken (survivent au crash bot)
- Thread daemon surveillant en continu
- Réconciliation au démarrage
- Lock pour accès concurrent

**⚠️ Risque mineur :**
- `_on_stop_loss_triggered` non initialisé dans `__init__` (seulement dans `start()`). Risque théorique faible.

---

## 2. 💰 SÉCURITÉ FINANCIÈRE

### 2.1 Calculs P&L — Exactitude, arrondis

**✅ Bien fait :**
- Frais séparés (maker 0.16%, taker 0.26%)
- Net profit = gross - fees
- Prix réel d'exécution depuis Kraken
- Opération atomique SQLite (close + record trade)

**⚠️ Risques :**

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| F1 | **Pas de `Decimal`** — Float partout. Erreurs ~10⁻¹⁵ s'accumulent. | Haute | Mineur | **Partielle** — OK paper trading |
| F2 | **Frais hardcodés** — Si tier Kraken change, P&L faux | Moyenne | Mineur | **Partielle** |

### 2.2 Gestion du capital — Allocations, race conditions

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| F3 | **🔴 CRITIQUE — `_allocated_capital` dérive sans réconciliation** — `close_position()` soustrait `buy_price * volume`. Si le prix réel Kraken diffère (spread/slippage), la soustraction est inexacte. Après N trades, `_allocated_capital` peut devenir négatif ou surestimé → `get_available_capital()` retourne un faux montant → positions au-delà du capital réel OU refus de trader. **Et `_check_capital_divergence()` dans ReconciliationManager est un stub TODO vide.** | Moyenne | **Critique** | **Insuffisante** ⛔ |
| F4 | **Grid `on_price` utilise `get_current_capital()` (total) au lieu de `get_available_capital()` (libre)** — `available_capital = self.instance.get_current_capital()` inclut capital alloué. Permet d'acheter avec du capital déjà en position. | **Haute** | **Majeur** | **Insuffisante** ⛔ — Fix: `get_available_capital()` |
| F5 | **Spin-off 500€ fixes** — Pas de vérification que l'instance a 500€ LIBRE (vs capital total). Le validator check le capital Kraken global, pas de l'instance. | Moyenne | Majeur | **Partielle** |

### 2.3 Ordres — Volumes, prix, minimums

**✅ Bien fait :**
- Grid: capital/niveau calculé une seule fois (anti-shrinking)
- Seuil vente min 1.5% (couvre frais ~1.04% + marge)
- Protection grid invalidation (2× range)
- Drawdown check par position (max 10%)
- Guard prix <= 0

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| F6 | **Pas de validation minimum Kraken** — Min 0.0001 BTC non vérifié avant envoi. Kraken rejettera avec `EOrder:Order minimum not met` mais pas géré spécifiquement. | Moyenne | **Majeur** | **Insuffisante** |
| F7 | **`_convert_symbol` — 4 paires hardcodées** — Fallback `replace('/', '')` | Faible | Mineur | **Partielle** — Seul BTC/EUR utilisé |

---

## 3. ⚡ RACE CONDITIONS & DEADLOCKS

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| R1 | **Grid `open_levels` désynchronisé si SL Kraken se déclenche** — StopLossManager ferme la position, mais Grid.`on_position_closed` n'est PAS appelé → `open_levels` croit la position ouverte → tente de re-vendre un niveau fermé | Moyenne | **Majeur** | **Insuffisante** ⛔ — Le wiring callback StopLossManager → Grid n'existe pas |
| R2 | **Double-lock Strategy.RLock → Instance.Lock** — Grid `on_price` sous RLock appelle `get_current_capital()` (Instance lock). Sûr SI Instance ne call jamais Strategy sous son lock. | Faible | Mineur | **Partielle** — En pratique sûr |
| R3 | **Signal BUY pendant emergency_stop** — Check atomique `status == RUNNING` dans `open_position()` sous lock. | Faible | Mineur | **Suffisante** ✅ |

**✅ Bien fait :** Callbacks hors lock partout, singletons protégés, `_instance_lock` correctement géré (stop/unsubscribe hors lock).

---

## 4. 💥 SCÉNARIOS DE CRASH

### 4.1 Crash pendant exécution ordre

| # | Scénario | Prob. | Impact | Mitigation |
|---|----------|:-:|:-:|:-:|
| C1 | **Crash APRÈS ordre Kraken accepté, AVANT position locale** — Position orpheline sur Kraken. | Faible | **Majeur** | **Insuffisante** — ReconciliationManager devrait détecter, mais `_get_kraken_orders()`, `_check_if_sold_on_kraken()`, `_get_average_sell_price()`, `_get_last_price()` sont des **stubs TODO vides**. |
| C2 | **Crash APRÈS BUY, AVANT pose stop-loss** — Position sans protection. | Faible | **Majeur** | **Partielle** — Position restaurée SQLite mais sans SL. Réconciliation tente de reposer. |

### 4.2 Crash pendant réconciliation

| # | Scénario | Prob. | Impact | Mitigation |
|---|----------|:-:|:-:|:-:|
| C3 | **Crash pendant `close_position_and_record_trade`** — SQLite transaction atomique protège. | Faible | Mineur | **Suffisante** ✅ |
| C4 | **Réconciliation partielle** — Au prochain démarrage, reprend de zéro. | Faible | Mineur | **Suffisante** ✅ |

### 4.3 WebSocket déconnecté pendant trade

| # | Scénario | Prob. | Impact | Mitigation |
|---|----------|:-:|:-:|:-:|
| C5 | **Prix stalé, pas de signal sell** | Moyenne | Mineur | **Suffisante** ✅ — SL sur Kraken, pas logiciel |
| C6 | **Reconnexion auto** — Heartbeat monitoring 10s, reconnexion backoff 1s→60s | — | — | **Suffisante** ✅ |

### 4.4 Rate limiting Kraken

| # | Scénario | Prob. | Impact | Mitigation |
|---|----------|:-:|:-:|:-:|
| C7 | **Rate limit pendant emergency** — Backoff exp, 3 retries/position | Moyenne | Mineur | **Suffisante** ✅ |

---

## 5. 📊 CONSISTANCE DONNÉES (SQLite vs Kraken)

| # | Risque | Prob. | Impact | Mitigation |
|---|--------|:-:|:-:|:-:|
| D1 | **SQLite "open" vs Kraken "closed"** — Si SL déclenché pendant downtime | Moyenne | **Majeur** | **Partielle** — StopLossManager.`reconcile_positions` vérifie au démarrage. Mais ReconciliationManager est largement inachevé (stubs TODO). |
| D2 | **Fichier log `autobot.log` peut contenir infos sensibles en DEBUG** | Faible | Mineur | **Partielle** — OK dev. Prod: rotation + permissions |

---

## 6. 🌐 DASHBOARD API

**✅ Bien fait :**
- Auth Bearer token (via `DASHBOARD_API_TOKEN` env var)
- Bind `127.0.0.1` par défaut (pas exposé au réseau)
- CORS restrictif (localhost:5173, localhost:3000)
- Methods limitées (GET, POST)
- Emergency stop nécessite confirmation `"CONFIRM_STOP"`
- Méthodes thread-safe (`get_status_safe`, `get_instances_snapshot`)
- Erreurs internes masquées (pas de stack traces exposées)
- Graceful shutdown via uvicorn.Server

**Aucun risque significatif identifié.**

---

## 7. 📝 RÉSUMÉ DES ACTIONS REQUISES

### 🔴 BLOQUANTS (à corriger AVANT paper trading)

| # | Fix | Effort | Fichier |
|---|-----|:-:|--------|
| **F3** | Ajouter réconciliation périodique `_allocated_capital` vs balance Kraken réelle. Au minimum : reset `_allocated_capital` = somme(positions ouvertes × buy_price × volume) à chaque réconciliation. | 2h | `instance.py` + `reconciliation.py` |
| **F4** | Remplacer `self.instance.get_current_capital()` par `self.instance.get_available_capital()` dans `grid.py:on_price()` | 5min | `grid.py` ligne ~260 |

### 🟡 IMPORTANTS (à corriger avant trading réel, OK pour paper)

| # | Fix | Effort | Fichier |
|---|-----|:-:|--------|
| **E2** | Étendre whitelist `_safe_api_call` : ajouter `ClosedOrders`, `Balance`, `TradeBalance` (ou supprimer la whitelist et router tout via `query_private`) | 15min | `order_executor.py` |
| **E5** | Remplacer `ValidatorEngine()` par `create_default_validator_engine()` dans SignalHandler | 5min | `signal_handler.py` |
| **E6** | Ajouter compteur erreurs consécutives + circuit breaker → `emergency_stop()` après 10 échecs API | 1h | `order_executor.py` ou `signal_handler.py` |
| **R1** | Wirer callback StopLossManager → Instance → Grid.`on_position_closed()` pour garder `open_levels` synchronisé | 1h | `stop_loss_manager.py` + `instance.py` |
| **F6** | Ajouter validation volume minimum Kraken (0.0001 BTC) avant envoi ordre | 15min | `order_executor.py` |
| **C1** | Implémenter les stubs TODO dans ReconciliationManager (`_get_kraken_orders`, `_check_if_sold_on_kraken`, etc.) | 3h | `reconciliation.py` |
| **F5** | Vérifier capital LIBRE de l'instance avant