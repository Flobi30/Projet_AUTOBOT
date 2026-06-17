# Research Symbol Alias Dedupe Non-Regression - 2026-06-17

## Verdict

PASS

## Scope

This patch deduplicates Kraken research collection targets after central symbol resolution. It prevents aliases such as `XRPEUR`, `XRPZEUR`, and `XXRPZEUR` from triggering duplicate OHLCV or spread/depth collection for the same Kraken market.

## Files Modified

- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/research/historical_data_collector.py`
- `src/autobot/v2/research/spread_depth_recorder.py`
- `tests/research/test_daily_data_collection_runner.py`
- `tests/research/test_historical_data_collector.py`
- `tests/research/test_spread_depth_recorder.py`

## Behavior Changed

- Daily research collection now normalizes configured and runtime symbols before preflight.
- Daily OHLCV and spread/depth collection now iterate over preflight-resolved canonical research symbols.
- Direct OHLCV and spread/depth collectors collapse aliases before fetching Kraken public endpoints.
- Alias mappings remain extensible through the central Kraken public pair preflight; missing future mappings should fail clearly instead of being silently ignored.

## Behavior Not Changed

- No paper trading execution logic changed.
- No live trading logic changed.
- No sizing, risk, strategy, router, governance, or duplication logic changed.
- No Kraken private API usage added.
- No orders can be created by this patch.

## Tests

Commands run locally:

```powershell
python -m py_compile src\autobot\v2\research\daily_data_collection_runner.py src\autobot\v2\research\historical_data_collector.py src\autobot\v2\research\spread_depth_recorder.py
$env:PYTHONPATH='src'; python -m pytest tests\research\test_daily_data_collection_runner.py tests\research\test_historical_data_collector.py tests\research\test_spread_depth_recorder.py tests\research\test_kraken_symbol_mapping.py -q
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Results:

- Focused tests: `15 passed`
- Research/CLI tests: `176 passed`
- Compile checks: passed

## Safety Confirmation

- `PAPER_TRADING` behavior unchanged.
- `LIVE_TRADING_CONFIRMATION` behavior unchanged.
- No strategy promotion path changed.
- No instance split/spin-off path changed.
- Runtime trading remains unaffected; this is research data collection plumbing only.

## Expected Operational Result

The next daily research collection should no longer double-count XRP aliases. With the current 14 active AUTOBOT markets and 3 OHLCV timeframes, readiness output should return 42 OHLCV symbol/timeframe rows instead of the alias-inflated 45 rows observed before this patch.
