# P18D Non-Regression - Alpha Runner Walk-Forward + Risk Mandate

Date: 2026-07-09  
Verdict: PASS_WITH_WARNINGS  
Final commit: `2a2b77ace3964db0a52d0700c9059c4eb859c88a`

## Files Modified

Code:

- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/strategy_risk_mandates.py`
- `tests/research/test_strategy_risk_mandates.py`

Reports/artifacts:

- `reports/research/alpha_hypothesis_runner/p18d_alpha_hypothesis_runner_walk_forward_20260709.json`
- `reports/research/alpha_hypothesis_runner/p18d_alpha_hypothesis_runner_walk_forward_20260709.md`
- `reports/research/alpha_hypothesis_runner/p18d_strategy_autonomy_check_20260709.json`
- `reports/research/p18d_volatility_breakout_walk_forward_mandate_2026-07-09.md`
- `reports/non_regression/2026-07-09_p18d_walk_forward_mandate_non_regression.md`

## What Changed

- `strategy-autonomy-check` now separates `passed_checks`, `failed_checks`, `blockers`, `warnings`, `final_decision`, `risk_direction`, and `human_review_required`.
- Research-only mandate blockers are explicit:
  - `mode_is_research_only`
  - `capital_max_eur_is_zero`
  - `paper_capital_allowed_false`
  - `runtime_orders_not_allowed`
- Auto-kill health reporting no longer marks `health` as a blocker when the decision is `ALLOW`.
- No runtime trading logic, paper executor, router runtime, UI, sizing, leverage, or live flag was changed.

## Tests Run

Local:

```bash
python -m compileall -q src
```

Result: PASS

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_strategy_risk_mandates.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_volatility_breakout_walk_forward.py tests\test_v2_cli.py -q
```

Result: 47 passed

Previously in the same P18D cycle:

```bash
$env:PYTHONPATH='src'; python -m pytest tests\paper -q
```

Result: 72 passed

```bash
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py -q
```

Result: 46 passed

VPS research container:

```bash
python -m compileall -q src
```

Result: PASS

## VPS State

- GitHub/local/VPS commit: `2a2b77ace3964db0a52d0700c9059c4eb859c88a`
- Container `autobot-v2`: healthy
- `/health`: healthy
- WebSocket: connected
- Instances: 14
- Main container restart: not performed

Flags:

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset/false

## P18D Runner Evidence

Command:

```bash
python -m autobot.v2.cli alpha-hypothesis-runner \
  --hypothesis-id volatility_breakout \
  --mode walk_forward \
  --state-db /app/data/autobot_state.db \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/alpha_hypothesis_runner \
  --run-id p18d_alpha_hypothesis_runner_walk_forward_20260709 \
  --max-variants 5 \
  --max-symbols 6 \
  --max-runtime-seconds 300 \
  --commit 2a2b77ace3964db0a52d0700c9059c4eb859c88a
```

Result:

- DATA_CHECK: KEEP_RESEARCH, passed
- FAST_NET_EDGE_TEST: KEEP_RESEARCH, passed
- WALK_FORWARD: REJECT, failed
- Stress/Monte-Carlo: not run because walk-forward failed
- Paper capital/live/promotion: false

## Risks / Warnings

- PASS_WITH_WARNINGS because the runner P18D JSON currently exposes full gate metrics and concentration artifacts, but fold tables are still easier to read from the specialized walk-forward report. This is a reporting ergonomics gap, not a trading safety regression.
- `volatility_breakout` is rejected by walk-forward and must not be promoted.

## Trading Safety Confirmation

- No live order was created.
- No paper capital was activated.
- No strategy was promoted.
- No runtime order path was touched.
- No router runtime integration was added.
- No paper executor integration was added.
- No sizing/leverage changed.
- Grid remains blocked/no-go.

## Recommendation

Safe to proceed only to a research/reporting P18E. Do not activate volatility_breakout in shadow, paper capital, or live. Improve runner report detail and evaluate the next alpha hypothesis through the same bounded gates.
