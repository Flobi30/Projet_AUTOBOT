# prompts/market_data_providers.md
## System
You are an expert in financial data APIs.
## User
Generate adapters for:
- Alpha Vantage (REST)
- Twelve Data (WebSocket + REST)
- CCXT (crypto)
For each:
1. Class reading API key from env.
2. Method get_data(symbol, since) → DataFrame.
3. Register in data/providers.py.
4. Pytest mocks.
## Output
- src/data/providers.py
- tests/test_providers.py
