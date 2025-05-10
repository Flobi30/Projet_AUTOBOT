Dans src/autobot/backtest_engine.py :
- Crée une fonction `run_backtest(strategy_name: str, parameters: dict) -> dict` qui :
  1. Importe et instancie `StrategyManager` depuis `src/autobot/strategies.py`.
  2. Appelle `manager.run_backtest(strategy_name, parameters)`.
  3. Retourne le dict de métriques (`sharpe_ratio`, `total_return`, `max_drawdown`).
- Dans `src/autobot/router.py`, modifie l’endpoint POST `/backtest` pour qu’il :
  1. Appelle `run_backtest(...)` à la place des valeurs simulées.
  2. Conserve le même schéma de sortie Pydantic `BacktestResult`.
Ajoute un commentaire `# REAL_BACKTEST`.
