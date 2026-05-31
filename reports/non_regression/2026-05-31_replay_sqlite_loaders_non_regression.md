# Non-Regression - Replay SQLite Loaders

Commit: `c03980f`
Date: `2026-05-31`
Verdict: `PASS_WITH_WARNINGS`

## Scope

Added read-only SQLite data loaders to the isolated research replay harness:

- `ResearchValidationHarness.load_market_events_from_state_db()`
- `ResearchValidationHarness.load_market_events_from_trade_ledger()`
- `ResearchValidationHarness.load_market_events_from_paper_trades_db()`

Added pytest coverage for:

- chronological loading from `market_price_samples`;
- empty result when the expected table is absent;
- execution-trace loading from `trade_ledger`;
- execution-trace loading from `paper_trades.db`.

## Files Changed

- `src/autobot/v2/research_validation_harness.py`
  - Added read-only SQLite helpers.
  - Added AUTOBOT state DB market sample loader.
  - Added trade ledger execution-trace loader.
  - Added paper trades execution-trace loader.
  - No runtime order routing, live execution, sizing, risk, dashboard, or strategy behavior changed.

- `tests/test_research_validation_harness.py`
  - Added SQLite fixture tests for the new loaders.
  - Existing replay, ledger, metrics, baseline, and live-block tests remain covered.

## What Did Not Change

- Dashboard routes and frontend: unchanged.
- Paper executor runtime behavior: unchanged.
- Live trading behavior: unchanged.
- Strategy router: unchanged.
- Risk management: unchanged.
- Kraken order execution: unchanged.
- Docker configuration: unchanged.
- Persistent production data: read-only probe only; no migration or write.

## Local Validation

Commands:

```powershell
python -m py_compile src\autobot\v2\research_validation_harness.py
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py -q
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py tests\test_strategy_router.py tests\test_quant_validation.py -q
$env:PYTHONPATH='src'; python -m compileall -q src
git diff --check
```

Results:

- `py_compile`: passed.
- Harness tests: `12 passed`.
- Targeted non-regression suite: `40 passed`.
- `compileall`: passed.
- `git diff --check`: no whitespace errors.

Note: `compileall` and pytest regenerated tracked `.pyc` files locally; those generated artifacts were restored and are not part of the commit.

## VPS Validation

Commands:

```bash
cd /opt/Projet_AUTOBOT
git pull --ff-only
git rev-parse --short HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_research_validation_harness.py tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_quant_validation.py -q
docker compose ps
curl http://127.0.0.1:8080/health
```

Results:

- VPS updated to `c03980f`.
- Targeted VPS suite: `40 passed`.
- Docker: `autobot-v2` is `Up` and `healthy`.
- `/health`: HTTP `200`, orchestrator running, websocket connected, `14` instances.
- Authenticated API probes: `/api/status`, `/api/capital`, `/api/trading/debug`, `/api/quant/validation` all returned HTTP `200`.

Read-only loader probe on VPS:

```json
{
  "state_db_exists": true,
  "paper_db_exists": true,
  "market_sample_events_loaded": 25,
  "trade_ledger_events_loaded": 25,
  "paper_trade_events_loaded": 25
}
```

The `25` counts were limited probes, not full table counts.

## Trading Safety

- The harness remains isolated from Kraken and runtime execution.
- New loaders are read-only and cannot create orders.
- No strategy can be promoted live by this change.
- `live_auto_promotion_allowed` remains false in the harness decision path.
- No permissive fallback was added to the router or promotion gate.
- No live sizing, leverage, risk, or execution parameter was changed.

## Warnings

- VPS logs still show intermittent websocket backpressure warnings.
- Logs also show strategy governance pauses and setup optimizer pauses for underperforming pairs.
- These warnings are runtime observations, not introduced by the SQLite loader change, but they remain worth monitoring.

## Recommendation

Safe to proceed to the next validation step: use the market sample loader as the preferred replay source, and use trade/paper execution traces only for audit reconstruction. Do not treat execution-trace events as complete market history.
