# Non-Regression - Paper/Research Diagnostics - 2026-06-04

## Verdict

PASS_WITH_WARNINGS

Paper/research comparison buckets now include diagnostics that explain the
likely investigation path for each alignment or divergence, without changing
runtime paper trading, live trading, strategy routing, or the registry.

## Changes

- `src/autobot/v2/research/paper_research_comparison.py`
  - Added per-bucket `diagnostics`.
  - Added diagnostics to JSON and Markdown reports.
  - Examples include `runtime_or_sample_difference`,
    `router_risk_or_execution_gap`, `research_adapter_missing_official_paper_trades`,
    `paper_sample_too_small`, and
    `research_cost_breakdown_unavailable_from_matrix_summary`.
- `tests/research/test_paper_research_comparison.py`
  - Added assertions for divergence diagnostics and Markdown output.

## What Must Not Have Changed

- Dashboard: not touched.
- Paper trading runtime: not touched.
- Live trading: not touched.
- Strategy router / promotion gate: not touched.
- Risk management / sizing / leverage: not touched.
- Docker/VPS configuration: not touched.
- Persistent runtime data: not touched.

## Trading Safety

- Report-only change.
- No order path is invoked.
- No registry mutation is performed.
- No live trading permission is granted.

## Validation Evidence

Commands:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m py_compile src\autobot\v2\research\paper_research_comparison.py tests\research\test_paper_research_comparison.py
python -m pytest tests\research\test_paper_research_comparison.py tests\test_v2_cli.py::test_cli_compare_paper_research_reports_divergence tests\test_v2_cli.py::test_cli_compare_paper_research_accepts_validate_strategies_output -q
python -m pytest tests\research tests\paper tests\risk tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted comparison tests: `5 passed in 0.47s`.
- Broader research/paper/risk/CLI tests: `122 passed in 1.22s`.
- Compile checks: passed.

## Smoke Evidence

Temporary nested `validate-strategies` comparison smoke produced:

```json
{
  "alignment": "paper_positive_research_negative",
  "diagnostics": [
    "runtime_or_sample_difference",
    "paper_sample_too_small",
    "research_sample_too_small",
    "paper_profit_factor_unavailable",
    "research_cost_breakdown_unavailable_from_matrix_summary",
    "research_rejected_negative_net_pnl"
  ],
  "live_note": "No live trading permission is granted."
}
```

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

- Diagnostics are bucket-level heuristics, not a full event-by-event decision
  trace reconciliation.
- Matrix summaries still do not expose detailed fees/slippage breakdown per
  bucket; loss attribution reports contain richer cost context.
- This does not mutate strategy statuses or promote execution.

## Recommendation

Next roadmap step: connect the decision trace audit with paper/research
comparison so each divergence can point to signal generation, router/risk gate,
fill simulation, or official paper execution evidence.
