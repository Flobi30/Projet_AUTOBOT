# 🚨 PLAN DE CORRECTION MASSIVE - AUTOBOT V2

## Objectif : Rendre le bot production-ready

---

## PHASE 1 : EXÉCUTION RÉELLE DES ORDRES (P0 - Bloquant)

### 1.1 OrderExecutor - Module d'exécution Kraken
**Fichier à créer :** `src/autobot/v2/order_executor.py`

**Responsabilités :**
- Exécuter les ordres BUY/SELL via API Kraken (`AddOrder`)
- Attendre confirmation et récupérer prix d'exécution réel
- Gérer ordres partiellement remplis
- Rate limiting avec backoff
- Logging sécurisé (masquer clés API)

**Interface :**
```python
class OrderExecutor:
    def execute_buy(symbol: str, volume: float) -> OrderResult
    def execute_sell(symbol: str, volume: float) -> OrderResult  
    def execute_stop_loss(symbol: str, volume: float, stop_price: float) -> OrderResult
    def get_order_status(txid: str) -> OrderStatus
    def cancel_order(txid: str) -> bool
```

### 1.2 Correction SignalHandler
**Fichier :** `src/autobot/v2/signal_handler.py`

**Modifications :**
- `_execute_buy()` : Utiliser OrderExecutor au lieu de `instance.open_position()` direct
- `_execute_sell()` : Utiliser OrderExecutor au lieu de `instance.close_position()` direct
- Attendre confirmation avant de mettre à jour l'état local
- Utiliser prix d'exécution réel, pas prix du signal

### 1.3 Correction Instance
**Fichier :** `src/autobot/v2/instance.py`

**Modifications :**
- `open_position()` : Prendre txid + fill_price en paramètre (pas de calcul local)
- `close_position()` : Même chose
- `_close_all_positions_market()` : Vérifier positions réelles avant de vendre

---

## PHASE 2 : MATHÉMATIQUES CORRECTES (P0 - Perte d'argent)

### 2.1 Grid Strategy - Seuil de vente
**Fichier :** `src/autobot/v2/strategies/grid.py`

**Correction :**
```python
# AVANT (perd argent):
self._sell_threshold_pct = max(0.5, grid_step * 0.8)

# APRÈS (rentable):
# Frais Kraken taker ~0.52% (entrée + sortie = ~1.04%)
# Marge minimum 0.5% → total 1.5%
self._sell_threshold_pct = max(1.5, grid_step * 0.8)
```

### 2.2 Grid Strategy - Capital disponible
**Correction :**
```python
# AVANT :
available = self.instance.get_current_capital()

# APRÈS :
available = self.instance.get_available_capital()  # Capital non alloué
```

### 2.3 Trend Strategy - Sizing
**Fichier :** `src/autobot/v2/strategies/trend.py`

**Correction :**
```python
# AVANT (50% = suicide) :
volume = PositionSizing.percentage_capital(available, 50) / price

# APRÈS (20% = raisonnable) :
volume = PositionSizing.percentage_capital(available, 20) / price
```

### 2.4 Grid Levels - Formule géométrique
**Fichier :** `src/autobot/v2/strategies/__init__.py`

**Correction :**
```python
# AVANT (arithmétique - asymétrique) :
offset = -half_range + (i * step)

# APRÈS (géométrique - symétrique) :
# Niveaux en progression géométrique autour du centre
```

---

## PHASE 2 : STOP-LOSS SUR EXCHANGE (P0 - Protection) ✅ COMPLÉTÉ

### 2.1 Ordres stop-loss natifs Kraken
**Fichier :** `src/autobot/v2/order_executor.py` ✅

**Implémentation :**
- ✅ `execute_stop_loss_order()` - Pose ordre stop-loss sur Kraken
- ✅ Retry logic avec backoff
- ✅ Récupération txid

### 2.2 StopLossManager - Surveillance et synchronisation
**Fichier :** `src/autobot/v2/stop_loss_manager.py` ✅ NOUVEAU

**Implémentation :**
- ✅ Surveillance continue des stop-loss (thread dédié)
- ✅ Réconciliation au démarrage (positions fermées pendant offline)
- ✅ Annulation automatique lors de fermeture manuelle
- ✅ Callback quand stop-loss déclenché

### 2.3 Intégration Position et Instance
**Fichiers :** `src/autobot/v2/instance.py`, `signal_handler.py` ✅

**Modifications :**
- ✅ Position dataclass avec `stop_loss_txid` et `stop_loss_triggered`
- ✅ `open_position()` accepte et stocke `stop_loss_txid`
- ✅ Persistence du txid dans SQLite
- ✅ SignalHandler pose stop-loss AVANT création position locale

---

## PHASE 3 : SÉCURITÉ & ROBUSTESSE (P1)

---

## PHASE 4 : SÉCURITÉ & ROBUSTESSE (P1)

### 4.1 Réconciliation état local ↔ exchange
**Fichier à créer :** `src/autobot/v2/reconciliation.py`

**Responsabilités :**
- Au démarrage : comparer positions locales vs positions Kraken
- Détecter divergences (positions orphelines, manquantes)
- Corriger état local si nécessaire
- Job périodique (toutes les heures)

### 4.2 Singletons thread-safe
**Fichiers :** `persistence.py`, `risk_manager.py`

**Correction :**
```python
# Ajouter lock pour création singleton
_singleton_lock = threading.Lock()

with _singleton_lock:
    if _instance is None:
        _instance = Class()
```

### 4.3 WebSocket heartbeat
**Fichier :** `src/autobot/v2/websocket_client.py`

**Correction :**
- Thread dédié pour heartbeat (toutes les 10s)
- Détection prix stalé (> 30s sans update)
- Reconnexion automatique avec backoff exponentiel

### 4.4 Validateurs réellement utilisés
**Fichier :** `src/autobot/v2/signal_handler.py`

**Correction :**
- `_execute_buy()` : Appeler `validator.validate('open_position', context)` AVANT exécution
- `_execute_sell()` : Idem
- Respecter le verdict (GREEN/YELLOW/RED)

---

## PHASE 5 : CORRECTIONS MINEURES (P2)

### 5.1 Frais dynamiques Kraken
- Récupérer frais réels via API (`TradeVolume`)
- Stocker dans config
- Utiliser pour calcul P&L

### 5.2 Emergency mode réversible
- Ajouter méthode `reset_emergency_mode()`
- Condition : prix revenu dans la grille + 5% marge
- Timeout maximum (ex: 24h)

### 5.3 Double-achat protection
- Set `_pending_levels` pour marquer niveaux avec ordre en cours
- Vérifier avant d'émettre signal

### 5.4 CancelAll scoped
- Utiliser `userref` pour identifier ordres du bot
- Annuler seulement ceux avec ce userref

---

## PHASE 6 : TESTS (P0)

### 6.1 Tests unitaires
- OrderExecutor (mock Kraken API)
- Mathématiques stratégies
- Gestion erreurs

### 6.2 Tests d'intégration
- Paper trading Kraken (API de test)
- Scénarios : crash, reconnexion, ordre partiel

### 6.3 Tests end-to-end
- Dry-run 48h en conditions réelles
- Monitoring capital, P&L, divergence

---

## ESTIMATION TEMPS

| Phase | Durée estimée | Priorité |
|-------|---------------|----------|
| Phase 1 : Exécution réelle | 3-4 jours | P0 🔴 |
| Phase 2 : Mathématiques | 1 jour | P0 🔴 |
| Phase 3 : Stop-loss exchange | 2 jours | P0 🔴 |
| Phase 4 : Sécurité | 2-3 jours | P1 🟡 |
| Phase 5 : Mineures | 1 jour | P2 🟢 |
| Phase 6 : Tests | 2-3 jours | P0 🔴 |
| **TOTAL** | **11-14 jours** | |

---

## PROCHAINES ACTIONS IMMÉDIATES

1. **Créer OrderExecutor** - Module central d'exécution
2. **Corriger seuil Grid** - 0.5% → 1.5%
3. **Corriger sizing Trend** - 50% → 20%
4. **Implémenter stop-loss exchange**

Commencer par laquelle ?
