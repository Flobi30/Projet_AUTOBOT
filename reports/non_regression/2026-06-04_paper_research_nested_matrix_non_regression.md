# Non-Regression - Paper/Research Nested Matrix Compatibility - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

`compare-paper-research` and `leaderboard` can now consume either a raw matrix
JSON report or the combined `validate-strategies` workflow JSON where the
matrix is nested under `matrix`.

## Changes

- `src/autobot/v2/research/registry_recommendations.py`
  - `load_matrix_result()` accepts both raw matrix JSON and nested
    `validate-strategies` workflow JSON.
- `tests/research/test_registry_recommendations.py`
  - Added loader coverage for nested workflow JSON.
- `tests/test_v2_cli.py`
  - Added CLI comparison coverage using a nested `validate-strategies` payload.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading runtime: not touched.
- Live trading: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Docker/VPS configuration: not touched.
- Persistent runtime data: not touched.

## Trading Safety

- This is a read-only report compatibility change.
- No paper or live orders are created.
- No strategy registry mutation is performed.
- No live trading permission is granted.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\research\registry_recommendations.py tests\research\test_registry_recommendations.py tests\test_v2_cli.py
python -m pytest tests\research\test_registry_recommendations.py tests\research\test_paper_research_comparison.py tests\test_v2_cli.py::test_cli_compare_paper_research_reports_divergence tests\test_v2_cli.py::test_cli_compare_paper_research_accepts_validate_strategies_output -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted loader/comparison tests: `11 passed in 0.38s`.
- Broader research/paper/risk/CLI tests: `122 passed in 1.08s`.
- Compile checks: passed.

## Smoke Evidence

Temporary CLI smoke with:

- Paper journal: `trend_momentum/TRXEUR`, `+5.0 EUR` net.
- Nested `validate-strategies` JSON: research `trend/TRXEUR`, `-2.5 EUR` net.

Result:

- `matrix_run_id`: `smoke_matrix_nested`.
- `bucket_count`: `1`.
- `divergent_bucket_count`: `1`.
- Alignment: `paper_positive_research_negative`.
- Recommendation: `investigate_runtime_or_sample_difference`.
- Safety notes include:
  - `Read-only paper/research comparison.`
  - `No paper or live order is created.`
  - `No strategy registry mutation is performed.`
  - `No live trading permission is granted.`

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

- The comparison still summarizes by strategy/symbol bucket; it does not yet
  explain individual paper decision paths against individual replay decisions.
- JSON files written manually by older Windows PowerShell with a UTF-8 BOM can
  still require clean encoding or loader hardening.
- This does not update the strategy registry automatically by design.

## Recommendation

Next roadmap step: enrich paper/research comparison with decision-path and
cost attribution so divergences explain whether the issue is signal generation,
router/risk gating, fill simulation, or paper execution.
