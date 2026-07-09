# P18C Alpha Hypothesis Runner - p18d_alpha_hypothesis_runner_walk_forward_20260709

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.
- Commit: `2a2b77ace3964db0a52d0700c9059c4eb859c88a`.
- Hypothesis: `volatility_breakout`.
- Runner mode: `walk_forward`.
- Final status: `REJECT`.
- Final decision: `STOPPED`.

## Architecture

Market data research store -> hypothesis registry -> autonomy policy -> sequential gates -> report.

## Gates

| Gate | Status | Passed | Stopped | Autonomy | Risk | Runtime s | Reasons |
|---|---|---:|---:|---|---|---:|---|
| `DATA_CHECK` | `KEEP_RESEARCH` | True | False | `AUTO_ALLOWED` | `neutral` | 26.619303 | data_ready |
| `FAST_NET_EDGE_TEST` | `KEEP_RESEARCH` | True | False | `AUTO_ALLOWED` | `neutral` | 53.285675 | positive_smoke_requires_walk_forward_before_shadow, no_shadow_or_paper_allowed |
| `WALK_FORWARD` | `REJECT` | False | True | `AUTO_ALLOWED` | `neutral` | 80.097337 | drawdown_above_12_pct_proxy, majority_folds_not_positive, positive_pnl_concentrated_in_one_symbol, fails_without_bcheur, fails_without_bcheur_adaeur |

## First Smoke Result

- `trade_count`: `206`
- `net_pnl_eur`: `10.992686`
- `profit_factor_net`: `1.0247690793047701`
- `expectancy_net`: `0.05336255339805825`
- `winrate_pct`: `36.89320388349515`
- `max_drawdown_eur`: `119.800035`
- `total_cost_bps`: `20188.0`
- `no_trade_baseline_eur`: `0.0`
- `by_symbol`: `{'ADAEUR': {'trade_count': 59, 'net_pnl_eur': 16.86005}, 'BCHEUR': {'trade_count': 51, 'net_pnl_eur': 93.768388}, 'ETHZEUR': {'trade_count': 23, 'net_pnl_eur': -2.761545}, 'SOLEUR': {'trade_count': 43, 'net_pnl_eur': -64.437705}, 'XRPZEUR': {'trade_count': 30, 'net_pnl_eur': -32.436502}}`
- `by_period`: `{}`
- `adapter_decision`: `KEEP_RESEARCH`
- `best_variant`: `fixed_tp_sl__min500bps__rr2__hold72h`
- `variant_count`: `3`

## Autonomy Policy

- `auto_allowed_gates`: `['DATA_CHECK', 'FAST_NET_EDGE_TEST', 'WALK_FORWARD', 'STRESS_MONTE_CARLO']`
- `human_review_gates`: `['SHADOW_REVIEW_CANDIDATE']`
- `principle`: `AUTOBOT may automatically reduce risk, but may never automatically increase risk.`

## Safety

- Research-only alpha hypothesis runner.
- No runtime order path is imported or called.
- No paper capital, live activation, promotion, sizing, leverage, or UI path is changed.
- Risk-reducing actions may be automatic; risk-increasing actions require human review.
- paper_capital_allowed: `False`
- live_allowed: `False`
- promotable: `False`

## Recommendation P18D

Continue with the next research-only gate only if explicitly requested by CLI mode; no paper/live promotion.
