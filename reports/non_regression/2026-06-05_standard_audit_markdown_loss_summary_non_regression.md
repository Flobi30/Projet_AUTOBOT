# Non-Regression Report - Standard Audit Markdown Loss Summary

Date: 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change makes the main `standard-audit` Markdown report surface the matrix
loss-attribution summary when either full standard reports or quick aggregate
loss attribution are available.

Changed files:

- `src/autobot/v2/research/standard_audit_runner.py`
  - Adds a read-only Markdown summary row for loss attribution.
  - Adds a Markdown artifact link to either the full loss-attribution report or
    the quick aggregate loss-attribution report.
- `tests/test_v2_cli.py`
  - Extends the quick standard-audit CLI test to verify the Markdown includes
    the loss summary and quick report link.

## Expected Non-Changes

- Dashboard: not touched.
- Paper trading runtime: not touched.
- Live trading runtime: not touched.
- Strategy router and promotion gate: not touched.
- Risk management, sizing, leverage, order execution: not touched.
- Existing APIs and Docker compose configuration: not touched.
- Persistent runtime databases: not touched.

## Safety

This is a reporting-only change. It does not alter research calculations,
strategy routing, cost assumptions, risk gates, paper execution, or live
execution.

No strategy candidate, learning strategy, or shadow result can pass live through
this change because no live or promotion code path is modified.

## Validation Commands

Focused tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py::test_cli_standard_audit_can_skip_matrix_annex_reports tests/research/test_loss_attribution.py -q
```

Result:

```text
4 passed in 0.30s
```

Broad research/paper regression suite:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
127 passed in 1.70s
```

Python compile:

```powershell
python -m compileall -q src
```

Result: passed.

Quick standard audit smoke:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli standard-audit --run-id vps_2026_06_05_grid_markdown_loss_summary --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db --strategies grid --timeframe 5m --output-dir reports/research/vps_2026_06_05_grid_markdown_loss_summary --dataset-output-dir data/research/vps_2026_06_05_grid_markdown_loss_summary --include-regime-context --skip-standard-reports --min-closed-trades 1 --train-window-bars 20 --test-window-bars 10 --step-window-bars 10 --min-folds 1 --min-passing-folds 1 --decision-trace-sample-limit 50
```

Result: completed successfully.

Markdown evidence from the generated standard audit:

```text
| Loss attribution | 484 trades, gross `-178.6692` EUR, net `-333.5492` EUR, cost `232.3200` EUR, MFE/cost `0.9620`, exit capture `-36.8819` bps |
- Quick loss attribution report: `reports\research\vps_2026_06_05_grid_markdown_loss_summary\quick_loss_attribution\vps_2026_06_05_grid_markdown_loss_summary_matrix_matrix_loss_attribution.md`
```

## Runtime VPS Check

Public health command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","timestamp":"2026-06-05T17:27:44.939615+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":652288.081037}}
```

Warning: this report confirms public `/health`, but it does not claim a full
Docker log audit because the previous SSH attempt in this work session was
denied with `Permission denied (publickey,password)`.

## Risks

- PASS_WITH_WARNINGS is used because Docker logs were not available through SSH.
- This change is presentation-only. It makes evidence more visible, but it does
  not improve strategy performance by itself.

## Recommendation

Proceed. The standard audit Markdown is now easier to use for triage: it exposes
whether losses come from gross PnL, costs, MFE/cost, or exit capture without
requiring manual JSON inspection.
