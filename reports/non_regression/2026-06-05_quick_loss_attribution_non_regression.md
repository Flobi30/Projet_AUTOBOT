# Non-Regression Report - Quick Loss Attribution

Date: 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change keeps a lightweight aggregate loss-attribution report available when
the standard audit runner is launched with `--skip-standard-reports`.

Changed files:

- `src/autobot/v2/research/standard_audit_runner.py`
  - In quick mode, writes aggregate matrix loss attribution with
    `write_cell_reports=False`.
  - Adds the serialized result under
    `matrix.quick_loss_attribution_report`.
- `tests/test_v2_cli.py`
  - Extends the quick-mode CLI regression test to prove the aggregate loss
    attribution exists and does not write per-cell attribution reports.
- `docs/research/CLI_WORKFLOWS.md`
  - Documents that quick mode keeps aggregate loss attribution while skipping
    slow per-cell annex reports.

## Expected Non-Changes

- Dashboard: not touched.
- Paper trading runtime: not touched.
- Live trading runtime: not touched.
- Strategy router and promotion gate: not touched.
- Risk management, sizing, leverage, order execution: not touched.
- Existing APIs and Docker compose configuration: not touched.
- Persistent runtime databases: not touched by this code change.

## Safety

The modified runner remains read-only:

- It does not start AUTOBOT runtime services.
- It does not create paper or live orders.
- It does not mutate the strategy registry.
- It does not grant live trading permission.
- It does not alter strategy selection, thresholds, cost guard, risk, sizing, or
  execution behavior.

No strategy candidate, learning strategy, or shadow result can pass live through
this change because live routing and promotion code paths are not modified.

## Validation Commands

Focused quick-mode and loss-attribution tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py::test_cli_standard_audit_can_skip_matrix_annex_reports tests/research/test_loss_attribution.py -q
```

Result:

```text
4 passed in 0.33s
```

Broad research/paper regression suite:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
127 passed in 2.05s
```

Python compile:

```powershell
python -m compileall -q src
```

Result: passed.

Quick standard audit smoke:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli standard-audit --run-id vps_2026_06_05_grid_quick_loss_audit --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db --strategies grid --timeframe 5m --output-dir reports/research/vps_2026_06_05_grid_quick_loss_audit --dataset-output-dir data/research/vps_2026_06_05_grid_quick_loss_audit --include-regime-context --skip-standard-reports --min-closed-trades 1 --train-window-bars 20 --test-window-bars 10 --step-window-bars 10 --min-folds 1 --min-passing-folds 1 --decision-trace-sample-limit 50
```

Result: completed successfully.

Key smoke evidence:

- Matrix cells: 14.
- Loss-attribution analyzed cells: 14.
- Replay grid trades analyzed: 484.
- Aggregate gross PnL: `-178.66919478190255 EUR`.
- Aggregate net PnL: `-333.5491947819025 EUR`.
- Aggregate costs: `232.3200000000001 EUR`.
- Cost-flipped trades: 82.
- Trades with MFE above cost: 194.
- Trades with MFE above cost but lost: 8.
- Average MFE: `48.101250808080394 bps`.
- Average MAE: `-113.1530750410264 bps`.
- Average exit capture: `-36.88192915258553 bps`.
- Average MFE giveback: `84.98317996066591 bps`.
- Average MFE-to-cost ratio: `0.9620250161616078`.

Interpretation: the current quick replay evidence shows grid loss is not only a
fee problem. Gross PnL is already negative before costs; fees/spread/slippage
then worsen the net result. The dominant research direction remains signal
quality, market-regime suitability, and exit behavior rather than simply
lowering thresholds or trading more.

Top loss-attribution cells from the smoke run:

| Symbol | Trades | Gross PnL EUR | Net PnL EUR | Cost EUR | Cost-Flipped | MFE > Cost | MFE > Cost Lost | Avg MFE bps | Avg Exit Capture bps | Worst Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| XLMZEUR | 131 | -17.5254 | -59.4454 | 62.8800 | 14 | 73 | 5 | 64.6767 | -13.3661 | grid_stop_loss |
| BCHEUR | 53 | -22.0492 | -39.0092 | 25.4400 | 10 | 22 | 1 | 45.7600 | -41.5648 | grid_stop_loss |
| ADAEUR | 32 | -17.7801 | -28.0201 | 15.3600 | 9 | 8 | 0 | 40.0406 | -55.5129 | grid_stop_loss |
| ATOMEUR | 22 | -20.1702 | -27.2102 | 10.5600 | 1 | 8 | 0 | 32.6091 | -91.6004 | grid_stop_loss |
| AVAXEUR | 29 | -15.8503 | -25.1303 | 13.9200 | 0 | 9 | 0 | 41.8201 | -54.6069 | grid_stop_loss |

## Runtime VPS Check

Public health command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","timestamp":"2026-06-05T17:16:24.277026+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":651607.41844}}
```

SSH Docker log check attempted:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 root@204.168.251.201 "cd /opt/Projet_AUTOBOT && docker compose ps && docker logs --tail 80 autobot 2>&1 | tail -80"
```

Result:

```text
Permission denied (publickey,password).
```

Warning: this report confirms public `/health`, but it does not claim a full
Docker log audit because SSH was not available from this session.

## Risks

- PASS_WITH_WARNINGS is used because Docker logs could not be read through SSH.
- The quick audit smoke intentionally skipped slow per-cell standard reports.
  It is useful for triage, not final strategy promotion evidence.
- The smoke evidence still shows paper/research divergence buckets and stale or
  incomplete traceability. Those are existing research findings, not introduced
  by this change.

## Recommendation

Proceed to the next research-validation step. Use quick mode for wide triage,
then run full standard reports only on narrowed candidate strategy/symbol
buckets. Do not promote grid or increase risk based on this evidence.
