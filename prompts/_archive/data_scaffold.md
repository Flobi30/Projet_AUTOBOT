# prompts/data_scaffold.md

## System
You are a senior Python developer. Generate a new module `data` for AUTOBOT.

## User
Create a Python package `data/` that:
1. Fetches real‑time market data from a configurable list of APIs.
2. Normalizes raw JSON into pandas DataFrame with schema: timestamp, symbol, open, high, low, close, volume.
3. Includes type hints, docstrings, and error handling.
4. Provides a CLI entry point `python -m data.fetch --symbol BTC-USD --since 2025-01-01`.
5. Comes with two unit tests using pytest and a mock CSV.

## Output
- Files under `src/data/`: `__init__.py`, `loader.py`, `fetch.py`.
- Tests under `tests/test_data_fetch.py`.
