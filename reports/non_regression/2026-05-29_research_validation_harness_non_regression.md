# Non-Regression - Research Validation Harness - 2026-05-29

Verdict: PASS_WITH_WARNINGS

## Scope

Commit tested: `6926913 Add research validation replay harness`

Files changed:

- `src/autobot/v2/research_validation_harness.py`
  - Adds an isolated event-driven replay harness for research validation only.
  - Standardizes replay events: market, signal, risk decision, simulated order/fill, ledger entry, metrics, baselines and validation decision.
  - Adds realistic simulated execution controls for fees, spread, slippage, liquidity rejection, limit order rejection and latency metadata.
  - Adds replay ledger export support and automatic validation run reports.
  - Generates registry update proposals without applying them.
- `tests/test_research_validation_harness.py`
  - Adds tests for chronological replay, no look-ahead price history, cost/slippage accounting, ledger/report generation, baselines, rejection behavior and live-promotion blocking.
- `reports/validation_runs/trend_momentum_replay_example_2026_05_29.md`
  - Example replay report on existing `TrendStrategy` adapter with synthetic data.

## What Must Not Have Changed

- Dashboard: not modified.
- Runtime paper trading: not modified.
- Live trading execution: not modified.
- Strategy router and promotion gate: not modified.
- Production risk management: not modified.
- Docker configuration: not modified.
- Persistent DB/data schemas: not modified.

The harness is imported only when explicitly used by tests/research code. It is not wired into the running orchestrator, dashboard router, paper executor or Kraken execution path.

## Trading Safety

- No live order path was touched.
- No Kraken client or real order executor is used by the harness.
- `RiskDecision.checks["live_order_allowed"]` is always `False`.
- `HarnessValidationDecision.live_promotion_allowed` is always `False`.
- Registry proposals set `live_auto_promotion_allowed=false`.
- A replay can recommend only research statuses such as `candidate` or `backtest_passed`; it does not apply registry changes automatically.
- The 14 runtime instances visible in `/health` are unaffected and do not bypass the existing promotion gate.

## Tests

Local commands:

```powershell
python -m py_compile .\src\autobot\v2\research_validation_harness.py
$env:PYTHONPATH='src'; python -m pytest .\tests\test_research_validation_harness.py -q
$env:PYTHONPATH='src'; python -m pytest .\tests\test_strategy_validation_registry.py .\tests\test_strategy_router.py .\tests\test_quant_validation.py .\tests\test_research_validation_harness.py -q
python -m compileall -q .\src
```

Local results:

- `py_compile`: PASS
- New harness tests: `8 passed`
- Targeted non-regression suite: `36 passed`
- `compileall`: PASS

Additional local check:

```powershell
$env:PYTHONPATH='src'; python -m pytest --collect-only -q
```

Result: `1000 tests collected`.

Warning:

- Full `python -m pytest -q` timed out after 184 seconds.
- Full `python -m pytest -m "not e2e and not external" -q` also timed out after 184 seconds.
- This is not attributed to the new harness because the targeted suites pass locally and on VPS, but the full-suite timeout should be tracked separately if a complete CI wall-clock target is required.

VPS commands:

```bash
cd /opt/Projet_AUTOBOT && git pull --ff-only && git rev-parse --short HEAD
cd /opt/Projet_AUTOBOT && PYTHONPATH=src python3 -m pytest tests/test_research_validation_harness.py -q
cd /opt/Projet_AUTOBOT && python3 -m py_compile src/autobot/v2/research_validation_harness.py
cd /opt/Projet_AUTOBOT && PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_quant_validation.py tests/test_research_validation_harness.py -q
cd /opt/Projet_AUTOBOT && python3 -m compileall -q src
```

VPS results:

- Pulled to `6926913`.
- New harness tests: `8 passed`.
- Targeted non-regression suite: `36 passed`.
- `py_compile`: PASS.
- `compileall`: PASS.

## Runtime VPS

Runtime checks:

- `docker compose ps autobot`: `Up ... (healthy)`.
- `curl http://127.0.0.1:8080/health`: `status=healthy`, orchestrator running, websocket connected, `instances=14`.
- Protected API without token: `401`, expected.
- Protected API with token read locally on VPS without printing it:
  - `/api/status`: `200`
  - `/api/capital`: `200`
  - `/api/trading/debug`: `200`
  - `/api/quant/validation`: `200`
- `docker logs --tail 80 autobot-v2` filtered for `error|critical|exception|traceback|real order|live`: no matching critical output.

Docker was not rebuilt because this change is an isolated research module and is not imported by the running app. The VPS working tree has the code available for offline validation runs after `git pull`.

## Risks Remaining

- The harness is a first production-quality skeleton, not a full HFT-grade simulator.
- The random baseline is deterministic and simple; it is adequate as a guardrail but not a statistical benchmark suite yet.
- Existing strategies are adapted through a compatibility adapter; strategy-specific replay adapters may be needed for async/grid internals.
- Full local test suite timeout remains a tooling/CI hygiene item.
- This does not prove a strategy is profitable; it proves that future strategy decisions can now be measured through a safer replay pipeline.

## Recommendation

Safe to proceed to the next validation step with PASS_WITH_WARNINGS:

1. Add real historical/paper dataset loaders for the trade ledger and market tick archives.
2. Run the harness on current grid/trend/mean-reversion candidates over larger samples.
3. Compare replay results against official paper trades to identify execution/model drift.
4. Keep live trading blocked until human review and existing paper/live promotion rules pass.
