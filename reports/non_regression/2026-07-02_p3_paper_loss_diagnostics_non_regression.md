# P3 Paper Loss Diagnostics Non-Regression - 2026-07-02

## Verdict

PASS

## Scope

P3 adds a read-only diagnostic layer for post-P2 `shadow_paper` losses. It does not change live trading, paper-capital execution, strategy parameters, sizing, leverage, dashboard layout, or runtime flags.

## Files Modified

- `src/autobot/v2/paper/loss_diagnostics.py`
  - New read-only diagnostics over attributed `shadow_paper` ledger records.
  - Separates gross PnL, net PnL, fees, slippage, gross PF, net PF, expectancy, drawdown, holding time, and segment attribution.
  - Produces segment views by strategy, symbol, timeframe, and regime.
  - Keeps `trend_momentum` and `mean_reversion` as `shadow_only` and blocks paper-capital promotion when net PF is not above 1.
  - Diagnoses `high_conviction_swing` missing closed shadow source data.
  - Treats `opportunity_scoring` only as a score/filter layer, not alpha.
- `src/autobot/v2/cli.py`
  - Adds `paper-loss-diagnostics` CLI command.
- `tests/paper/test_loss_diagnostics.py`
  - Adds targeted tests for attributed shadow-paper filtering, gross/net PF, cost isolation, segment grouping, disabled-segment blocking, opportunity-scoring filter behavior, and CLI report output.

## Explicit Non-Changes

- No live trading flag changed.
- No paper-capital route enabled.
- No order-routing logic changed.
- No strategy parameters changed.
- No sizing, leverage, risk, or execution thresholds changed.
- No dashboard visible design changed.
- No Grid reactivation.
- No strategy promotion.
- No Kraken order path touched.

## Trading Safety

- Legacy/unattributed trades remain excluded from official diagnostics.
- `dynamic_grid` is not part of the diagnostic strategy set and remains blocked by existing runtime policy.
- `trend_momentum` and `mean_reversion` remain `shadow_only` while net PF is <= 1.
- `opportunity_scoring` is reported as a filter/scoring layer only.
- `high_conviction_swing` is not judged from synthetic or missing closed-trade data.

## Tests Run

```text
python -m py_compile src\autobot\v2\paper\loss_diagnostics.py src\autobot\v2\cli.py tests\paper\test_loss_diagnostics.py
```

Result: PASS

```text
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_loss_diagnostics.py -q
```

Result: `6 passed in 0.27s`

```text
$env:PYTHONPATH='src'; python -m pytest tests\paper tests\test_v2_cli.py tests\test_pf_phase2.py tests\test_strategy_validation_registry.py -q
```

Result: `80 passed in 2.01s`

```text
python -m compileall -q src
```

Result: PASS

## Risks Remaining

- The final P3 conclusions depend on the VPS `autobot_state.db` after deployment and CLI execution there.
- `high_conviction_swing` still needs a real closed shadow source before performance can be measured.
- `opportunity_scoring` needs score metadata coverage on shadow trades before bucket analysis is useful.

## Recommendation

Deploy the read-only diagnostic, run `paper-loss-diagnostics` against the VPS state DB, and use the produced JSON/Markdown report to decide P4. Do not promote or allocate paper capital based on current P3 code alone.
