# Non-Regression - Replay Harness PnL Accounting - 2026-05-31

Verdict: PASS

## Scope

Commit tested: `024699b Align replay harness PnL accounting`

Files changed:

- `src/autobot/v2/research_validation_harness.py`
  - Avoids double-counting slippage in realized net PnL. Slippage remains reported as cost attribution, but execution prices already include it.
  - Adds explicit run counters: market events, generated signals, simulated orders and fills.
  - Adds explicit PnL metrics: realized gross PnL, realized net PnL and total net PnL.
- `tests/test_research_validation_harness.py`
  - Adds assertions that a fully closed replay has `realized_net_pnl_eur == total_net_pnl_eur == final_equity - initial_capital`.
  - Verifies event/signal/order/fill counters.
- `reports/validation_runs/trend_momentum_replay_example_2026_05_29.md`
  - Regenerated with corrected PnL and replay counters.

## What Did Not Change

- Dashboard: not modified.
- Runtime paper trading: not modified.
- Live trading execution: not modified.
- Strategy router and promotion gate: not modified.
- Production risk management: not modified.
- Docker configuration: not modified.
- Persistent database schemas/data: not modified.

The change remains isolated to the research validation harness and its report/test coverage.

## Trading Safety

- No Kraken client or real order executor touched.
- No live flag changed.
- No strategy promotion rule changed.
- No order sizing/risk behavior changed in runtime paper/live code.
- The harness still sets live promotion to false and only produces registry proposals.

## Tests

Local commands:

```powershell
$env:PYTHONPATH='src'; python -m pytest .\tests\test_research_validation_harness.py -q
$env:PYTHONPATH='src'; python -m pytest .\tests\test_strategy_validation_registry.py .\tests\test_strategy_router.py .\tests\test_quant_validation.py .\tests\test_research_validation_harness.py -q
python -m py_compile .\src\autobot\v2\research_validation_harness.py
python -m compileall -q .\src
```

Local results:

- Harness tests: `8 passed`
- Targeted validation/router/quant suite: `36 passed`
- `py_compile`: PASS
- `compileall`: PASS

VPS commands:

```bash
cd /opt/Projet_AUTOBOT && git pull --ff-only && git rev-parse --short HEAD
cd /opt/Projet_AUTOBOT && PYTHONPATH=src python3 -m pytest tests/test_research_validation_harness.py -q
cd /opt/Projet_AUTOBOT && PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_quant_validation.py tests/test_research_validation_harness.py -q
cd /opt/Projet_AUTOBOT && python3 -m py_compile src/autobot/v2/research_validation_harness.py && python3 -m compileall -q src
```

VPS results:

- Pulled to `024699b`
- Harness tests: `8 passed`
- Targeted validation/router/quant suite: `36 passed`
- `py_compile`/`compileall`: PASS

## Runtime VPS

- `docker compose ps autobot`: `Up 2 days (healthy)`
- `/health`: `status=healthy`, orchestrator running, websocket connected, `instances=14`
- Authenticated API checks:
  - `/api/status`: `200`
  - `/api/capital`: `200`
  - `/api/trading/debug`: `200`
  - `/api/quant/validation`: `200`
- `docker logs --tail 80 autobot-v2` filtered for critical/error/live-order patterns: no matching critical output.

Docker was not rebuilt because the running application does not import this research harness. Runtime behavior is unchanged.

## Result Of The Correction

The example report now shows:

- Market events replayed: `11`
- Signals generated: `2`
- Simulated orders: `2`
- Fills: `2`
- Realized gross PnL: `0.634593`
- Realized net PnL: `0.313321`
- Total net PnL: `0.313321`

For the closed trade in the example, realized net PnL now matches the final equity delta. Slippage is still visible as `0.120334` EUR but is not subtracted twice.

## Risks Remaining

- The dataset remains synthetic; it proves accounting consistency, not strategy performance.
- Full project pytest still needs a separate slow-test split; this correction did not address test-suite runtime.
- Real historical/paper data loaders are still the next step before strategic conclusions.

## Recommendation

Safe to proceed to real paper/historical data integration for replay validation.
