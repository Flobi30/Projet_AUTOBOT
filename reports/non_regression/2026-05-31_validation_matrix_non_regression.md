# Non-Regression Report - Research Validation Matrix

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a research-only validation matrix. It runs selected strategy
families across selected symbols, aggregates backtest or walk-forward results,
and writes one JSON plus one Markdown comparison report.

It does not alter runtime trading.

## Files Changed

- `src/autobot/v2/research/validation_matrix.py`
  - Adds `MatrixRunConfig`.
  - Adds `run_validation_matrix()`.
  - Adds per-cell error capture.
  - Adds Markdown/JSON matrix report rendering.
- `src/autobot/v2/research/__init__.py`
  - Exports matrix types and runner.
- `tests/research/test_validation_matrix.py`
  - Covers strategy x symbol matrix execution.
  - Covers summary report output.
  - Covers partial failure handling without aborting the whole matrix.

## What Did Not Change

- No production strategy code changed.
- No official paper executor changed.
- No live executor changed.
- No strategy router changed.
- No risk manager changed.
- No dashboard/API runtime behavior changed.
- No Docker/VPS runtime state changed.
- No production DB writes were added.

## Trading Safety Confirmation

- Matrix runner is research-only.
- It cannot submit Kraken orders.
- It only invokes `run_validation()` and writes reports.
- It does not mutate the strategy registry.
- It does not mutate paper/live positions.
- It cannot bypass the promotion gate.
- Live trading remains untouched and disabled.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\validation_matrix.py tests\research\test_validation_matrix.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `34 passed in 0.31s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.24s`

```powershell
python -m compileall -q src
```

Result: PASS

Note: Python bytecode cache files touched by compile/test execution were restored
from Git so the final diff contains only source/tests/report changes.

## Risks / Limits

- Matrix quality depends on data quality; runtime samples still lack bid/ask and
  depth.
- Strategy configs are supplied explicitly; there is not yet a curated parameter
  registry per strategy family.
- The matrix reports evidence, but it still does not auto-promote or auto-reject
  registry entries.

## Recommendation

Next step: add a lightweight report-to-registry proposal layer that consumes a
matrix result and produces human-review recommendations without automatically
changing live or paper eligibility.
