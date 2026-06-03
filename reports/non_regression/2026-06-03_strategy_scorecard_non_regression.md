# Non-Regression Report - Research Strategy Scorecard

Date: 2026-06-03
Scope: research-only strategy scoring and validation matrix report integration.
Verdict: PASS_WITH_WARNINGS

## Summary

This change adds a conservative `StrategyScorecard` layer to AUTOBOT research validation. It converts existing validation evidence into a 0-100 score and a tier:

- `<50`: disabled / rejected
- `50-65`: backtest only
- `65-75`: shadow only
- `75-85`: paper candidate
- `>85`: human live review candidate

The scorecard is deliberately research-only. It never grants live permission and never mutates the runtime strategy registry, router, paper execution, Kraken integration, capital allocation, or dashboard.

## Files Changed

- `src/autobot/v2/research/strategy_scorecard.py`
  - New scoring module.
  - Adds `StrategyEvidence`, `StrategyScorecardCriteria`, `StrategyScorecardResult`, `StrategyScorecardReport`.
  - Adds `score_strategy`, `score_matrix`, `render_strategy_scorecard_report`, `write_strategy_scorecard_report`.
  - Applies conservative caps for missing fees/slippage, missing baseline, non-positive net PnL, insufficient sample, missing out-of-sample evidence, and baseline underperformance.

- `src/autobot/v2/research/validation_matrix.py`
  - Adds explicit CLI flag `--write-strategy-scorecard`.
  - When requested, writes scorecard reports under `<output_dir>/strategy_scorecard`.
  - Default behavior is unchanged.

- `src/autobot/v2/research/__init__.py`
  - Adds lazy exports for the new scorecard types and functions.

- `tests/research/test_strategy_scorecard.py`
  - New focused scorecard tests.

- `tests/research/test_validation_matrix.py`
  - Extends the existing CLI integration test to verify scorecard report creation and live-safety output.

## What Changed

The research pipeline can now produce a strategy scorecard from:

- normalized `MetricsResult`;
- `WalkForwardResult`;
- aggregated `MatrixRunResult`.

The scorecard uses net PnL after costs, profit factor, expectancy, drawdown, sample size, baseline status, walk-forward status, and regime breadth. Missing scientific evidence caps the score instead of letting weak or incomplete evidence appear ready.

## What Did Not Change

Unchanged:

- Dashboard and frontend.
- Official paper execution.
- Live trading flags.
- Kraken order submission.
- Signal handler and order routing.
- Strategy router and promotion gate.
- Risk management.
- Position sizing and leverage.
- Existing validation matrix default output.
- Persistent trading data.
- Docker/VPS runtime behavior.

## Trading Safety

Confirmed:

- `live_promotion_allowed` is always `False`.
- A high score can only produce `human_review_only`, not live activation.
- Missing fees or slippage caps the score below execution tiers.
- Missing baselines caps the score below execution tiers.
- Non-positive net PnL is rejected.
- No fallback permissive router was added.
- No strategy registry mutation is performed.
- No order creation, fill creation, paper trade, or live trade path was changed.

## Validation Commands

Initial sandbox attempt:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\strategy_scorecard.py tests\research\test_strategy_scorecard.py src\autobot\v2\research\__init__.py
```

Result: blocked by Windows sandbox `Access denied`; rerun with approved escalation.

Compile targeted files:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\strategy_scorecard.py src\autobot\v2\research\validation_matrix.py src\autobot\v2\research\__init__.py tests\research\test_strategy_scorecard.py tests\research\test_validation_matrix.py
```

Result: PASS

Scorecard tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_scorecard.py -q
```

Result: `6 passed in 0.21s`

Scorecard + validation matrix integration tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_scorecard.py tests\research\test_validation_matrix.py -q
```

Result: `9 passed in 0.25s`

Full research suite:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `71 passed`

Compile all backend source:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Runtime VPS

The VPS/container was not restarted for this research-only change. No runtime code path is affected unless a human explicitly runs the validation matrix with `--write-strategy-scorecard`.

Recommended later runtime/research usage:

```powershell
python -m autobot.v2.research.validation_matrix --run-id <run_id> --data-source autobot_state_db --data-path <db_path> --symbols TRXEUR,BTCEUR --write-strategy-scorecard
```

## Risks And Warnings

- The score formula is an initial conservative governance heuristic. It should be calibrated with more official paper and replay evidence before being used for automated registry proposals.
- Matrix scorecards default `baseline_included=False` unless the scorecard is generated together with regime baselines, so scores remain capped when baselines are missing.
- This does not solve profitability; it improves the decision process for rejecting or containing weak strategies.

## Recommendation

Proceed to the next roadmap item after commit/push. The next missing structural pieces are:

1. `RiskManagerV2` as a research/runtime contract, without changing live behavior.
2. `PaperTradingEngine` daily reporting that uses the same evidence fields as backtest reports.
3. A small unified CLI wrapper around existing research commands.
