Dans src/autobot/router.py :
- Ajoute un endpoint POST `/trade` qui prend un JSON :
  ```json
  { "symbol": "BTC/USDT", "side": "buy", "amount": 0.01 }
  ```
- Importe `from autobot.trading import execute_trade`.
- Appelle `execute_trade(symbol, side, amount)` (stub dans `src/autobot/trading.py`).
- Retourne `{ "status": "order_placed", "order_id": "<id>" }`.
Crée `src/autobot/trading.py` avec la fonction stub `execute_trade()` qui utilise CCXT.  
Ajoute un commentaire `# REAL_TRADE`.
