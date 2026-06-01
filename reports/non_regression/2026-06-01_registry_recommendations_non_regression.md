# Non-Regression Report - Registry Recommendations

Date: 2026-06-01
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a research-only recommendation layer that consumes validation
matrix results and produces human-review strategy registry recommendations.

It also makes `autobot.v2` runtime exports lazy so importing
`autobot.v2.research` no longer loads the runtime orchestrator and its
paper/live dependencies during research tests.

## Files Changed

- `src/autobot/v2/research/registry_recommendations.py`
  - Adds conservative matrix-to-registry recommendation logic.
  - Adds JSON matrix loading.
  - Adds Markdown/JSON recommendation report rendering.
  - Never mutates `docs/research/strategy_hypotheses.json`.
  - Always sets `live_promotion_allowed=false`.
- `src/autobot/v2/research/__init__.py`
  - Exports recommendation dataclasses and helpers.
- `src/autobot/v2/__init__.py`
  - Replaces eager runtime imports with lazy exports.
  - Keeps public names such as `Orchestrator`, `TradingInstance`, and
    `RiskManager` available through `from autobot.v2 import ...`.
  - Prevents research imports from pulling paper/live runtime dependencies.
- `tests/research/test_registry_recommendations.py`
  - Covers workflow-safe recommendations.
  - Covers rejection on negative aggregate evidence.
  - Covers insufficient-sample keep-testing behavior.
  - Covers walk-forward recommendations.
  - Covers matrix JSON loading and report writing.

## What Did Not Change

- No production strategy logic changed.
- No official paper executor changed.
- No live executor changed.
- No order routing changed.
- No risk sizing, leverage, or execution rules changed.
- No dashboard/API endpoint changed.
- No persistent data or registry JSON was modified.
- No Docker/VPS deployment was performed by this change.

## Trading Safety Confirmation

- Recommendations are research-only and human-review-only.
- The module cannot submit Kraken orders.
- It cannot execute official paper orders.
- It cannot mutate the strategy registry.
- It cannot bypass `strategy_validation_registry`.
- A `learning` strategy cannot skip directly to `backtest_passed`; the report
  recommends only the next workflow-safe step.
- All recommendations keep `live_promotion_allowed=false`.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\__init__.py src\autobot\v2\research\registry_recommendations.py tests\research\test_registry_recommendations.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: PASS - `39 passed in 0.25s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.19s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Warnings / Environment Notes

- The local Windows Python environment initially did not contain `pytest`,
  `orjson`, or `pytest-asyncio`; these were installed in the user Python site
  packages to run the local tests.
- The VPS was not updated by this change, so this report proves local
  source-level non-regression only. Runtime VPS health should be checked again
  before or after any deployment.

## Risks / Limits

- The recommendation report depends on the quality of the input validation
  matrix. If the matrix is run on poor or tiny datasets, recommendations remain
  weak.
- Matrix cells currently expose fewer metrics than full backtest reports
  (for example no Sharpe/Sortino at the matrix summary level).
- The module proposes status changes but deliberately does not apply them.

## Recommendation

Next step: run the matrix on real AUTOBOT market-history datasets, generate
registry recommendation reports, then compare the recommendation output with
the existing `strategy_hypotheses.json` before any manual status change.
