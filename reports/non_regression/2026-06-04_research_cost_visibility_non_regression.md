# Non-Regression - Research Cost Visibility

Verdict: PASS

## Scope

Commit under validation: pending local change after `0af1c24`

Changed files:

- `src/autobot/v2/research/execution_cost_model.py`
- `src/autobot/v2/research/backtest_engine.py`
- `src/autobot/v2/research/validation_matrix.py`
- `src/autobot/v2/research/registry_recommendations.py`
- `src/autobot/v2/research/paper_research_comparison.py`
- `tests/research/test_execution_cost_model.py`
- `tests/research/test_backtest_engine.py`
- `tests/research/test_validation_matrix.py`
- `tests/research/test_registry_recommendations.py`
- `tests/research/test_paper_research_comparison.py`

Logic changed:

- `ExecutionCostConfig` now exposes a deterministic `to_dict()`.
- Backtest reports now include the exact cost assumptions used for a run.
- Matrix cells now carry net cost totals: fees, spread, slippage, latency.
- Matrix JSON now carries the run-level cost config.
- Matrix loader preserves those cost fields for downstream reports.
- Paper/research comparison now uses research cost breakdowns when available instead of treating matrix costs as unavailable.

Endpoints/routes touched: none.

Critical trading runtime touched: none.

## Expected Non-Changes

- Dashboard unchanged.
- Paper trading execution unchanged.
- Live trading execution unchanged.
- Strategy router unchanged.
- Risk management unchanged.
- Sizing/leverage unchanged.
- Runtime order submission unchanged.
- Docker/VPS behavior unchanged.
- Persistent runtime data unchanged.

## Trading Safety

- No live order path was modified.
- No Kraken integration was modified.
- No strategy promotion gate was modified.
- No fallback permissive behavior was added.
- The change is limited to research reporting, matrix serialization, and comparison diagnostics.
- Live promotion remains explicitly false in existing report contracts.

## Tests

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_execution_cost_model.py tests\research\test_backtest_engine.py tests\research\test_validation_matrix.py tests\research\test_registry_recommendations.py tests\research\test_paper_research_comparison.py -q
```

Result:

```text
26 passed in 0.54s
```

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Result:

```text
99 passed in 1.01s
```

Command:

```powershell
$env:PYTHONPATH='src'; python -m compileall -q src
```

Result: PASS

Command:

```powershell
git diff --check
```

Result: PASS, with Windows CRLF warnings only.

Skipped tests: none in the executed suites.

## Runtime VPS

Command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{
  "status": "healthy",
  "components": {
    "orchestrator": "running",
    "websocket": "connected",
    "instances": 14
  }
}
```

No restart was performed. No runtime mutation was performed.

## Risks

- This does not yet replace cost calculations in runtime paper/live modules. It makes research costs explicit and comparable.
- Older matrix reports without cost fields still load, but their downstream comparison may still show `research_cost_breakdown_unavailable_from_matrix_summary`.
- Shadow labs still have their own fee/slippage assumptions and need a separate parity pass.

## Recommendation

Proceed to the next roadmap step: align official paper/shadow/runtime cost assumptions with the research `ExecutionCostModel` contract, starting with read-only adapters and tests before touching any execution path.
