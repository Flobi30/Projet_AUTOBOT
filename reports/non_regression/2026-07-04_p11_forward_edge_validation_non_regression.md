# P11 Forward Edge Validation Non-Regression - 2026-07-04

## Verdict

PASS_WITH_WARNINGS

P11 adds a read-only forward-only validation layer for the P10 `forward_safe_net_edge` filter. It does not enable live trading, paper capital, strategy promotion, grid, sizing, leverage, or UI changes.

Warning: the local smoke database has no usable post-P10 observations, so the functional validation is limited to unit tests locally. VPS validation is expected after deployment against the live state DB.

## Files Modified

- `src/autobot/v2/paper/forward_edge_simulation.py`
  - Adds a forward-safe fallback to reconstruct `expected_move_bps` from pre-entry `expected_net_edge_bps + estimated_total_cost_bps` when both already exist.
  - Does not use post-trade fields.
- `src/autobot/v2/paper/forward_edge_validation.py`
  - New research-only/read-only P11 module.
  - Splits cohorts into pre-P10 and post-P10 using `record.opened_at >= cutoff`.
  - Supports known P10 commit cutoffs, including `85199ba235062d3cdc273d015ec67a573ad7d82e`.
  - Produces JSON/Markdown reports with coverage, scenarios, segment policy, and non-promotable forward-only result.
- `src/autobot/v2/cli.py`
  - Adds `forward-edge-validation`.
- `tests/paper/test_p6_score_and_confidence.py`
  - Adds P11 coverage for post-cutoff filtering, read-only CLI behavior, expected-move reconstruction from pre-trade net edge, insufficient-data separation, blocked segment separation, and non-promotion.

## Commands Run Locally

```powershell
python -m py_compile src\autobot\v2\paper\forward_edge_simulation.py src\autobot\v2\paper\forward_edge_validation.py src\autobot\v2\cli.py
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_p6_score_and_confidence.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_p6_score_and_confidence.py tests\paper\test_shadow_observation_sync.py tests\paper\test_loss_diagnostics.py tests\paper\test_official_performance.py -q
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\test_v2_cli.py tests\paper\test_p6_score_and_confidence.py tests\paper\test_shadow_observation_sync.py tests\paper\test_loss_diagnostics.py tests\paper\test_official_performance.py -q
$env:PYTHONPATH='src'; python -m autobot.v2.cli forward-edge-validation --state-db data\autobot_state.db --since-commit 85199ba235062d3cdc273d015ec67a573ad7d82e --no-write-report
```

## Local Test Results

- `tests/paper/test_p6_score_and_confidence.py`: 18 passed.
- Paper/reporting focused suite: 48 passed.
- Compileall: passed.
- CLI + paper focused suite: 75 passed.
- Local smoke `forward-edge-validation`: passed, no writes; local DB had `post_p10.eligible_trade_count=0`.

## Live Safety

- No live flag changed.
- No paper capital enabled.
- No strategy promoted.
- No order route changed.
- No grid activation.
- No sizing or leverage change.
- No UI change.

## Forward-Only Contract

- P11 cutoff criterion: `record.opened_at >= cutoff`.
- Known P10 code/report commit: `85199ba235062d3cdc273d015ec67a573ad7d82e`.
- All P11 scenarios set:
  - `promotable=false`
  - `paper_capital_allowed=false`
  - `live_allowed=false`
- `pre_p10` is reported but excluded from forward-only scenarios.

## VPS Validation

Pending deployment.

After deploy, run:

```bash
python -m autobot.v2.cli forward-edge-validation \
  --state-db data/autobot_state.db \
  --since-commit 85199ba235062d3cdc273d015ec67a573ad7d82e \
  --run-id p11_vps_forward_validation
```

## Recommendation

Deploy P11, run the forward validation on VPS, and keep collecting until the `forward_safe_net_edge_plus_score_high` post-P10 cohort has enough observations. It must remain shadow/research-only.
