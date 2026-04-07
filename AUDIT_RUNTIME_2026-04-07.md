# 🔍 AUDIT RUNTIME AUTOBOT — 7 Avril 2026

**Durée d'observation :** ~30 minutes (16:55 → 17:25 UTC)  
**Serveur :** 204.168.205.73 (Hetzner)  
**Container :** autobot-v2 (healthy)  

---

## DONNÉES BRUTES COLLECTÉES

### 1. Réponses API

**GET /api/status**
```json
{
    "running": true,
    "instance_count": 1,
    "total_capital": 1000.0,
    "total_profit": 0.0,
    "websocket_connected": true,
    "uptime_seconds": 1810
}
```

**GET /api/trades**
```json
{
    "count": 0,
    "trades": []
}
```

**GET /api/capital**
```json
{
    "total_capital": 1000.0,
    "total_profit": 0.0,
    "total_invested": 1000.0,
    "available_cash": 0.0,
    "currency": "EUR"
}
```

**GET /api/instances**
```json
[{
    "id": "ce3cd072",
    "name": "Instance Principale",
    "capital": 1000.0,
    "profit": 0.0,
    "status": "running",
    "strategy": "grid",
    "open_positions": 0
}]
```

**GET /api/performance/global**
```json
{
    "capital_total": 1000.0,
    "profit_total": 0.0,
    "profit_factor": 0.0,
    "win_rate": 0.0,
    "total_trades": 0,
    "instances_count": 1
}
```

**GET /api/paper-trading/summary**
```json
{
    "active_instances": 1,
    "paper_instances": 1,
    "is_paper_mode": true,
    "live_instances": 0,
    "pairs_tested": 1,
    "by_pair": [{
        "symbol": "BTC/EUR",
        "instance_count": 1,
        "total_trades": 0,
        "avg_profit_percent": 0.0,
        "avg_pf": 0.0,
        "win_rate": 0.0,
        "recommendation": "continue_paper"
    }]
}
```

**Base de données (SQLite)**
```
Tables existantes: (aucune table 'trades' trouvée)
sqlite3: "No trades table" / "No trades data"
```

### 2. Logs complets (30 min)

**Événements significatifs :**
- Grid initialisée au prix: 58,775.20€
- SmartRecentering (V3) active
- GridAsync [ADAPTIVE]: 15 niveaux, +/-4.0% sur 58775
- Market selector: "0 marchés disponibles" → "Aucun marché approprié trouvé pour spin-off"
- Healthcheck toutes les 60s: `Health: running=True instances=1 ws=True`

**Événements ABSENTS (en 30 min) :**
- ❌ AUCUN signal BUY émis
- ❌ AUCUN signal SELL émis
- ❌ AUCUN log de la Grid strategy (buy/sell levels)
- ❌ AUCUN log du SignalHandler
- ❌ AUCUN log du OrderExecutor
- ❌ AUCUN trade exécuté
- ❌ AUCUNE position ouverte
- ❌ AUCUN log de prix reçu (pas de "on_price" trace)

**Le seul trafic en 30 min :**
- Health checks (127.0.0.1)
- Requêtes dashboard API (213.245.216.48 — le navigateur de Flo)

### 3. Architecture — Modules wirés vs code mort

**BRANCHÉ ET ACTIF dans le runtime :**
| Module | Importé par | Utilisé ? |
|--------|------------|-----------|
| OrchestratorAsync | main_async.py | ✅ |
| OrderExecutorAsync | orchestrator_async.py | ✅ |
| StopLossManagerAsync | orchestrator_async.py | ✅ |
| KrakenWebSocketAsync | orchestrator_async.py | ✅ |
| RingBufferDispatcher | orchestrator_async.py | ✅ |
| AsyncDispatcher | orchestrator_async.py | ✅ |
| ValidatorEngine | orchestrator_async.py | ✅ |
| RiskManager | orchestrator_async.py | ✅ |
| GridStrategyAsync | instance_async.py (lazy) | ✅ |
| SignalHandlerAsync | instance_async.py (lazy) | ✅ |
| FeeOptimizer | instance_async.py (lazy) | ✅ |
| RegimeDetector | grid_async.py | ✅ (conditionnel) |
| FundingRates | grid_async.py | ✅ (conditionnel) |
| OpenInterest | grid_async.py | ✅ (conditionnel) |
| KellyCriterion | grid_async.py | ✅ (conditionnel) |
| HotPathOptimizer | orchestrator_async.py | ✅ |
| ColdPathScheduler | orchestrator_async.py | ✅ |
| ReconciliationAsync | orchestrator_async.py | ✅ |
| Persistence (SQLite) | orchestrator_async.py | ✅ |

**CODE MORT — Jamais importé/instancié dans le runtime :**
| Module | Fichier | Status |
|--------|---------|--------|
| ShadowTradingManager | shadow_trading.py | ❌ NON BRANCHÉ |
| DailyReporter | reports.py | ❌ NON BRANCHÉ |
| MeanReversionStrategy | strategies/mean_reversion.py | ❌ NON BRANCHÉ |
| TriangularArbitrage | strategies/arbitrage.py | ❌ NON BRANCHÉ |
| SentimentNLP | modules/sentiment_nlp.py | ❌ NON BRANCHÉ |
| HeuristicPredictor | modules/cnn_lstm_predictor.py | ❌ NON BRANCHÉ |
| XGBoostPredictor | modules/xgboost_predictor.py | ❌ NON BRANCHÉ |
| PairsTrading | modules/pairs_trading.py | ❌ NON BRANCHÉ |
| OnChainData | modules/onchain_data.py | ❌ NON BRANCHÉ |
| DCAHybrid | modules/dca_hybrid.py | ❌ NON BRANCHÉ |
| MicroGrid | modules/micro_grid.py | ❌ NON BRANCHÉ |
| LiquidationHeatmap | modules/liquidation_heatmap.py | ❌ NON BRANCHÉ |
| BlackSwan | modules/black_swan.py | ❌ NON BRANCHÉ |
| MomentumScoring | modules/momentum_scoring.py | ❌ NON BRANCHÉ |
| MultiIndicatorVote | modules/multi_indicator_vote.py | ❌ NON BRANCHÉ |
| VWAP/TWAP | modules/vwap_twap.py | ❌ NON BRANCHÉ |
| VolatilityWeighter | modules/volatility_weighter.py | ❌ NON BRANCHÉ |
| PyramidingManager | modules/pyramiding_manager.py | ❌ NON BRANCHÉ |
| TrailingStopATR | modules/trailing_stop_atr.py | ❌ NON BRANCHÉ |
| StrategyEnsemble | strategy_ensemble.py | ❌ NON BRANCHÉ |
| RebalanceManager | rebalance_manager.py | ❌ NON BRANCHÉ |
| AutoEvolution | auto_evolution.py | ❌ NON BRANCHÉ |
| MarketAnalyzer | market_analyzer.py | ❌ NON BRANCHÉ |
| MultiGridOrchestrator | strategies/multi_grid_orchestrator.py | ❌ NON BRANCHÉ |

### 4. Paper Trading — Le VRAI problème

**L'OrderExecutorAsync n'a AUCUNE logique paper trading.**

Le fichier `order_executor_async.py` :
- Se connecte à l'API Kraken réelle (HMAC-SHA512 signing)
- Appelle `execute_market_order` → `_query_private("AddOrder", ...)`
- Il n'y a PAS de mode simulation/paper
- Pas de condition `if PAPER_TRADING: simulate()`
- Pas de `validate_only` flag

**Le `PAPER_TRADING=true` dans `.env`** semble n'être lu par PERSONNE dans le code runtime. C'est juste une variable d'environnement qui flotte, inutilisée.

**Conséquence critique :** Si le Grid émet un signal BUY, il ira directement sur l'API Kraken réelle. Le "paper trading" n'existe peut-être pas tel qu'on le croit.

### 5. Pourquoi ZÉRO trade en 30 min ?

La Grid est configurée avec ±4% autour de 58,775€.

Les niveaux d'achat sont en dessous du prix actuel, les niveaux de vente au-dessus. Pour qu'un BUY se déclenche, le prix doit descendre vers les niveaux inférieurs de la grille.

**Mais le vrai problème :** Il n'y a AUCUN log de prix traité. Le WebSocket dit "subscribed" et "connected", mais après ça... silence total. Pas un seul `on_price` log, pas un seul tick traité en 30 minutes.

**Hypothèses :**
1. Les prix arrivent bien du WebSocket mais ne sont pas loggés (pas de log dans `on_price`) → le silence est "normal" si aucun niveau de grille n'est touché
2. Le dispatch des prix du WebSocket vers l'instance ne fonctionne pas
3. La queue entre AsyncDispatcher et l'instance est bloquée

Il faudrait ajouter un log temporaire dans `on_price` pour vérifier.

### 6. Base de données

SQLite existe (`autobot_state.db`, 36KB + WAL) mais **il n'y a pas de table `trades`**. Soit elle n'a jamais été créée, soit le schéma est différent.

---

## QUESTIONS À POSER À OPUS ET GEMINI

1. **Le paper trading existe-t-il vraiment ?** L'OrderExecutor n'a aucune logique de simulation. Qu'est-ce qui empêche un vrai ordre Kraken si un signal est émis ?

2. **Le WebSocket dispatch vers les instances fonctionne-t-il ?** 30 minutes sans un seul log de prix traité — est-ce normal ou le pipeline est cassé ?

3. **19 modules "performance" + 4 stratégies + Shadow Trading = TOUT du code mort.** Sur 40+ modules développés, seuls ~18 sont réellement wirés. Les tests passent en isolation mais rien n'est branché. Quelle est la valeur réelle de ces modules ?

4. **La base de données n'a pas de table trades.** Comment les trades sont-ils persistés ? Sont-ils persistés du tout ?

5. **Le market_selector dit "0 marchés disponibles".** Le spin-off automatique (nouvelles paires) ne fonctionne pas. Pourquoi ?

6. **available_cash: 0.0** — Tout le capital est "investi" (allocated), mais il y a 0 positions ouvertes. Incohérence ?

---

## RÉSUMÉ FACTUEL

| Métrique | Valeur |
|----------|--------|
| Uptime | 30 min, stable, aucun crash |
| WebSocket | Connecté (status: true) |
| Trades exécutés | **0** |
| Positions ouvertes | **0** |
| Profit | **0.00€** |
| Modules actifs | ~18 sur 40+ |
| Modules code mort | ~22+ |
| Paper trading vérifié | **NON — aucune logique paper dans OrderExecutor** |
| DB trades | **Table inexistante** |

---

*Données collectées le 2026-04-07 à ~17:25 UTC. Aucune interprétation — données brutes pour audit externe.*
