Dans src/autobot/router.py :
Ajoute un endpoint FastAPI POST `/backtest` qui accepte un JSON :
```json
{ "strategy": "mean_reversion", "parameters": { "window": 14 } }
```
Retourne un payload conforme au modèle Pydantic `BacktestResult` :
```json
{
  "strategy": "mean_reversion",
  "metrics": {
    "sharpe_ratio": 1.23,
    "total_return": 0.10,
    "max_drawdown": -0.05
  }
}
```
Placeholder : valeurs simulées.  
Ajoute un commentaire unique `# BASELINE_BACKTEST`.
