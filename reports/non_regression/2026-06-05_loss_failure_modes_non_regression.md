# Non-Regression Report - Loss Failure Modes

Date: 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change adds research-only failure-mode attribution to existing validation
loss reports. It helps explain why a strategy loses before changing runtime
strategy behavior.

Changed files:

- `src/autobot/v2/research/loss_attribution.py`
  - Adds `by_failure_mode` buckets to single-run and matrix loss-attribution
    reports.
  - Adds `primary_failure_mode` to each matrix cell.
  - Adds research-only recommendations based on the dominant failure mode.
- `src/autobot/v2/research/standard_audit_runner.py`
  - Shows the top failure mode in the main standard-audit Markdown summary.
- `tests/research/test_loss_attribution.py`
  - Covers failure-mode classification and report rendering.
- `tests/test_v2_cli.py`
  - Covers the main Markdown summary field in quick standard-audit mode.

## Expected Non-Changes

- Dashboard: not touched.
- Paper trading runtime: not touched.
- Live trading runtime: not touched.
- Strategy router and promotion gate: not touched.
- Risk management, sizing, leverage, order execution: not touched.
- Strategy thresholds, ATR, cost guard, fees, slippage, spread model: not
  changed.
- Existing APIs and Docker compose configuration: not touched.
- Persistent runtime databases: not mutated.

## Safety

This is a reporting-only validation change. It does not:

- start AUTOBOT runtime services;
- create paper or live orders;
- mutate the strategy registry;
- promote any strategy;
- authorize live trading;
- alter cost/risk/execution behavior.

No strategy candidate, learning strategy, shadow-only result, or runtime worker
can bypass the existing promotion gate through this change.

## Validation Commands

Focused tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/research/test_loss_attribution.py tests/test_v2_cli.py::test_cli_standard_audit_can_skip_matrix_annex_reports -q
```

Result:

```text
4 passed in 0.28s
```

Broad research/paper regression suite:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
127 passed in 1.95s
```

Python compile:

```powershell
python -m compileall -q src
```

Result: passed.

Quick standard audit smoke:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli standard-audit --run-id vps_2026_06_05_grid_failure_mode_audit --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db --strategies grid --timeframe 5m --output-dir reports/research/vps_2026_06_05_grid_failure_mode_audit --dataset-output-dir data/research/vps_2026_06_05_grid_failure_mode_audit --include-regime-context --skip-standard-reports --min-closed-trades 1 --train-window-bars 20 --test-window-bars 10 --step-window-bars 10 --min-folds 1 --min-passing-folds 1 --decision-trace-sample-limit 50
```

Result: completed successfully.

Smoke evidence:

- Trades analyzed: `484`.
- Aggregate gross PnL: `-178.66919478190255 EUR`.
- Aggregate net PnL: `-333.5491947819025 EUR`.
- Aggregate cost: `232.3200000000001 EUR`.
- Average MFE/cost: `0.9620250161616078`.
- Average exit capture: `-36.88192915258553 bps`.
- Dominant failure mode: `weak_mfe_below_cost`.

Failure-mode buckets:

| Failure Mode | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR |
|---|---:|---:|---:|---:|
| weak_mfe_below_cost | 156 | -352.821337 | -402.741337 | 74.880000 |
| cost_flipped_positive_gross | 82 | 23.772806 | -2.467194 | 39.360000 |
| profitable | 246 | 150.379336 | 71.659336 | 118.080000 |

Top affected cells:

| Symbol | Trades | Net PnL EUR | Primary Failure | Worst Exit | Avg MFE/Cost | Avg Exit Capture bps |
|---|---:|---:|---|---|---:|---:|
| XLMZEUR | 131 | -59.445384 | weak_mfe_below_cost | grid_stop_loss | 1.293533 | -13.366126 |
| BCHEUR | 53 | -39.009194 | weak_mfe_below_cost | grid_stop_loss | 0.915200 | -41.564845 |
| ADAEUR | 32 | -28.020122 | weak_mfe_below_cost | grid_stop_loss | 0.800813 | -55.512919 |
| ATOMEUR | 22 | -27.210228 | weak_mfe_below_cost | grid_stop_loss | 0.652181 | -91.600414 |
| AVAXEUR | 29 | -25.130255 | weak_mfe_below_cost | grid_stop_loss | 0.836403 | -54.606906 |
| AAVEEUR | 34 | -23.924568 | weak_mfe_below_cost | grid_stop_loss | 0.975715 | -38.331878 |
| BTCZEUR | 23 | -20.888222 | weak_mfe_below_cost | grid_stop_loss | 0.719928 | -58.765469 |
| DOTEUR | 29 | -20.013784 | weak_mfe_below_cost | grid_stop_loss | 0.914951 | -36.979765 |

Generated recommendation:

```text
Dominant failure mode: weak_mfe_below_cost.
Do not lower global thresholds first. Prioritize entry-quality filters: test wider grid spacing, stronger support confirmation, and regime/volatility filters so expected MFE clears costs.
```

Interpretation: the current evidence points toward weak grid entry quality
relative to costs and regime movement. This does not justify increasing size,
reducing safety, or forcing more trades.

## Runtime VPS Check

Public health command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","timestamp":"2026-06-05T19:48:01.123449+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":660704.264904}}
```

Warning: this report confirms public `/health`, but does not claim a full Docker
log audit. SSH was unavailable earlier in this work session with `Permission
denied (publickey,password)`.

## Risks

- PASS_WITH_WARNINGS is used because Docker logs were not available through SSH.
- Failure-mode labels are diagnostic buckets, not proof that a parameter change
  will be profitable.
- The smoke run is quick mode, useful for triage but not final strategy
  promotion evidence.

## Recommendation

Proceed to a research-only experiment that tests entry-quality improvements for
grid, especially wider spacing, stronger support confirmation, and regime or
volatility filters. Keep live disabled and do not increase risk until out-of-
sample replay and official paper evidence improve.
