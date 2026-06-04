# Non-Regression - Validate Strategies Workflow - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

The CLI now has a repeatable `validate-strategies` workflow that builds a
canonical research dataset from `market_price_samples`, runs the standard
strategy matrix, writes the standard report bundle, and keeps all outputs
research-only.

## Changes

- `src/autobot/v2/cli.py`
  - Added `validate-strategies`.
  - Refactored standard matrix report writing into a shared helper.
  - Workflow sequence:
    `build canonical dataset -> matrix -> registry recommendations -> loss attribution -> setup quality -> strategy/regime -> baselines -> walk-forward summary -> scorecard`.
- `tests/test_v2_cli.py`
  - Added an end-to-end CLI regression test for the new workflow.
- `docs/research/CLI_WORKFLOWS.md`
  - Documented the preferred one-command standard validation workflow.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading: not touched.
- Live trading: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Docker/VPS configuration: not touched.
- Persistent runtime DB data: read-only.

## Trading Safety

- No runtime service is started.
- No Kraken order path is invoked.
- No strategy registry mutation is performed.
- No live trading permission is granted.
- Scorecard and registry recommendations remain evidence only.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\cli.py tests\test_v2_cli.py
python -m pytest tests\test_v2_cli.py::test_cli_validate_strategies_builds_dataset_and_standard_matrix tests\test_v2_cli.py::test_cli_matrix_standard_reports_writes_full_research_bundle tests\test_v2_cli.py::test_cli_matrix_preset_fills_top14_symbols -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted CLI tests: `3 passed in 0.42s`.
- Broader research/paper/risk/CLI tests: `120 passed in 0.98s`.
- Compile checks: passed.

## Workflow Smoke

Read-only smoke on latest local VPS state DB snapshot:

```powershell
python -m autobot.v2.cli validate-strategies --run-id vps_validate_strategies_smoke --state-db <latest_vps_state_db> --symbols TRXEUR --strategies grid --timeframe 5m --min-closed-trades 1 --include-regime-context
```

Result summary:

- Dataset rows: `1975` 5m TRXEUR bars.
- Dataset gaps: `39`, max gap `1200s`.
- Matrix cells: `1`.
- Matrix errors: `0`.
- Closed trades: `10`.
- Net PnL: `-8.162958 EUR`.
- Profit factor: `0.065264`.
- Decision: `reject`.
- Live promotion allowed: `false`.
- Safety notes confirmed no runtime service, no Kraken order, no registry
  mutation, no live permission.

## VPS Runtime Check

Command:

```powershell
curl.exe -fsS http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

## Remaining Risks

- The command output can be verbose because standard reports include detailed
  report objects.
- Data gaps and missing volume remain dataset warnings.
- The command does not fetch external historical data yet.
- It does not update `strategy_hypotheses.json`; recommendations remain manual
  by design.

## Recommendation

Use `validate-strategies` as the default research validation entry point before
paper/router changes. Next roadmap step: strengthen paper official vs research
comparison using this standard matrix output.
