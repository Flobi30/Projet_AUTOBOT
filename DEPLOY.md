# DEPLOY.md

## Flags `ENABLE_*` et rôle

### Sécurité / Orchestrateur
- `ENABLE_CONFLICT_LOGGING` (default: `true`)
  - Active les logs de conflit entre signaux (grid vs mean reversion).
- `ENABLE_TRADING_HEALTH_SCORE` (default: `false`)
  - Active le calcul/alerte du health score global trading.

### Stratégies / Signaux
- `ENABLE_MEAN_REVERSION` (default: `false`)
  - Active le module mean-reversion dans le Decision Bus.
- `ENABLE_SENTIMENT` (default: `false`)
  - Active l’enrichissement du signal via SentimentNLP.
- `ENABLE_ONCHAIN` (default: `false`)
  - Active l’enrichissement OnChain dans l’évaluation de signal.
- `ENABLE_ML` (default: `false`)
  - Active le pipeline ML global (utilise XGBoost/heuristic).
- `ENABLE_XGBOOST` (default: `false`, fallback sur `ENABLE_ML`)
  - Active explicitement le sous-module XGBoost.

### Exécution / Capital
- `ENABLE_SHADOW_TRADING` (default: `true`)
  - Active le manager shadow trading (mode papier/validation).
- `ENABLE_SHADOW_PROMOTION` (default: `true`)
  - Autorise les promotions shadow -> live selon règles PF/trades.
- `ENABLE_REBALANCE` (default: `true`)
  - Active la boucle de rebalancing périodique.
- `ENABLE_AUTO_EVOLUTION` (default: `true`)
  - Active la boucle d’évolution automatique (phase/rollback).

---

## Ordre recommandé d’activation (Batch 1 → 2 → 3 → 5 → 4)

### Batch 1 (baseline sûr)
- `ENABLE_CONFLICT_LOGGING=true`
- `ENABLE_TRADING_HEALTH_SCORE=true`
- `ENABLE_SHADOW_TRADING=true`
- `ENABLE_SHADOW_PROMOTION=false`
- `ENABLE_REBALANCE=false`
- `ENABLE_AUTO_EVOLUTION=false`
- `ENABLE_MEAN_REVERSION=false`
- `ENABLE_SENTIMENT=false`
- `ENABLE_ONCHAIN=false`
- `ENABLE_ML=false`
- `ENABLE_XGBOOST=false`

### Batch 2 (risk controls)
- `ENABLE_REBALANCE=true`

### Batch 3 (signal enrichments non-ML)
- `ENABLE_MEAN_REVERSION=true`
- `ENABLE_ONCHAIN=true` (si clé/config node OK)

### Batch 5 (sentiment)
- `ENABLE_SENTIMENT=true` (si `SENTIMENT_API_KEY` + accès API externes)

### Batch 4 (ML/XGBoost, en dernier)
- `ENABLE_ML=true`
- `ENABLE_XGBOOST=true` (si modèle entraîné + features historiques disponibles)

---

## Variables d’environnement requises

### Requises pour démarrage minimal
- `AUTOBOT_AUTONOMOUS`
- `AUTOBOT_SAFE_MODE`
- `PAPER_TRADING`
- `INITIAL_CAPITAL`

### Requises pour dépendances optionnelles
- `SENTIMENT_API_KEY` (si `ENABLE_SENTIMENT=true`)
- `ONCHAIN_API_KEY` (si `ENABLE_ONCHAIN=true`)
- `ONCHAIN_NODE_URL` (si `ENABLE_ONCHAIN=true`)
- `XGBOOST_MODEL_PATH` (si `ENABLE_XGBOOST=true`)
- `HISTORICAL_DATA_PATH` (si `ENABLE_XGBOOST=true`)
- `SHADOW_TRADING_DB_PATH` (si `ENABLE_SHADOW_TRADING=true`)

### Runtime tuning (externalisés)
- `HEALTH_SCORE_THRESHOLD`
- `TRADE_ACTION_MIN_INTERVAL_S`
- `MAX_REPEATED_AUTO_ACTIONS`
- `MAX_BACKOFF_SECONDS`
- `MAX_INSTANCES_PER_CYCLE`
- `SPIN_OFF_THRESHOLD`
- `MIN_PF_FOR_SPINOFF`
- `TARGET_VOLATILITY`
- `WEBSOCKET_STREAMS`

---

## Commande de test avant déploiement

```bash
PYTHONPATH=src pytest -q tests/test_runtime_sanity.py tests/test_p0_spin_off_and_market_selector.py
```
