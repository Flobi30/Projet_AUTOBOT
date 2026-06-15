# Research Cost Evidence Parity Non-Regression - 2026-06-14

## Verdict

**PASS_WITH_WARNINGS**

The research cost-profile context and batch evidence plumbing are corrected.
Trading behavior did not change. Warnings relate to dataset quality only.

## Files Modified

- `src/autobot/v2/research/validation_runner.py`
  - propagates the selected research cost profile into grid expected-cost
    metadata while preserving explicit overrides.
- `src/autobot/v2/research/validation_matrix.py`
  - exposes baselines, MFE/cost and exit capture per matrix cell;
  - includes the evidence in JSON and Markdown reports.
- `src/autobot/v2/research/batch_strategy_validation.py`
  - replaces unconditional evidence-unavailable blockers with factual checks;
  - keeps a fail-closed result when evidence is absent or insufficient.
- `src/autobot/v2/cli.py`
  - exposes configurable batch thresholds for MFE/cost and exit capture.
- `tests/research/test_validation_runner.py`
- `tests/research/test_validation_matrix.py`
- `tests/research/test_batch_strategy_decision_thresholds.py`

## What Did Not Change

- dashboard;
- paper trading runtime;
- live trading runtime;
- strategy router and governance runtime;
- risk management and sizing;
- order execution;
- Kraken integration and credentials;
- persistent trading data;
- instance duplication/spin-off;
- Docker/VPS configuration.

No new strategy filter or exit rule was enabled. The replay produced the same
1,295 trades and the same net PnL values as before the patch.

## Commands And Results

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q
```

Result: `163 passed in 2.46s`.

Focused suite used during implementation:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/research/test_validation_runner.py tests/research/test_validation_matrix.py tests/research/test_batch_strategy_decision_thresholds.py tests/research/test_batch_strategy_validation.py tests/test_v2_cli.py -q
```

Result: `42 passed in 1.08s`.

Three frozen-dataset batch campaigns completed successfully with
`paper_current_taker`, `research_stress` and `research_legacy`.

## Replay Proof

| Profile | Before PnL | After PnL | Before trades | After trades | Grid expected cost after |
| --- | ---: | ---: | ---: | ---: | ---: |
| paper current taker | -1,190.800544 | -1,190.800544 | 1,295 | 1,295 | 94 bps |
| research stress | -1,242.605848 | -1,242.605848 | 1,295 | 1,295 | 98 bps |
| research legacy | -621.005848 | -621.005848 | 1,295 | 1,295 | 50 bps |

All strategies remain `research_only`. No registry mutation or automatic
promotion occurred.

## Trading Safety

Read-only VPS verification after the local work:

- deployed commit remains `28fa3e1`;
- container `autobot-v2`: running and healthy;
- `/health`: healthy;
- orchestrator: running;
- WebSocket: connected;
- instances: 14;
- `PAPER_TRADING=true`;
- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_LIVE_TRADING`: unset;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR`: unset;
- critical/traceback/live-order log matches over the last 30 minutes: 0.

No VPS restart, deployment, real order, paper order, strategy promotion,
position action, sizing change, risk change or split action was performed.

## Remaining Risks

- The frozen sample covers only seven days.
- The dataset contains 2,449 detected gaps.
- Real volume and observed order-book depth are unavailable.
- The random baseline is suitable as a child-run comparison but should remain
  interpreted alongside no-trade and buy-and-hold, never alone.

## Permission To Continue

The repository is safe to continue with longer data accumulation and
microstructure collection. It is not safe to promote any strategy, enable
live trading or activate instance duplication from this evidence.

