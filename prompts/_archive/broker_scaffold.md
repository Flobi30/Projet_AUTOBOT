# prompts/broker_scaffold.md
## System
You are a trading integration engineer.
## User
Scaffold package broker/:
1. Connect to Alpaca (paper) & Binance via REST/WebSocket.
2. Unified interface: Broker.place_order(symbol,side,qty).
3. Handle errors, reconnection, rate‑limits.
4. Pytest with HTTP/WebSocket mocks.
## Output
- src/broker/__init__.py, alpaca.py, binance.py, interface.py
- tests/test_broker.py
