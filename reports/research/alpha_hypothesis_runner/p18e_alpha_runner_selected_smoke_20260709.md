# P18C Alpha Hypothesis Runner - p18e_alpha_runner_selected_smoke_20260709

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.
- Commit: `None`.
- Hypothesis: `long_trend`.
- Runner mode: `smoke`.
- Final status: `REJECT_FAST`.
- Final decision: `STOPPED`.

## Architecture

Market data research store -> hypothesis registry -> autonomy policy -> sequential gates -> report.

## Gates

| Gate | Status | Passed | Stopped | Autonomy | Risk | Runtime s | Reasons |
|---|---|---:|---:|---|---|---:|---|
| `DATA_CHECK` | `KEEP_RESEARCH` | True | False | `AUTO_ALLOWED` | `neutral` | 25.906334 | data_ready |
| `FAST_NET_EDGE_TEST` | `REJECT_FAST` | False | True | `AUTO_ALLOWED` | `neutral` | 52.287579 | edge_net_not_positive, profit_factor_net_not_above_1, expectancy_net_not_positive |

## First Smoke Result

- `trade_count`: `404`
- `net_pnl_eur`: `-292.181428`
- `profit_factor_net`: `0.5992017913191805`
- `expectancy_net`: `-0.723221356435643`
- `winrate_pct`: `34.4059405940594`
- `max_drawdown_eur`: `294.092956`
- `total_cost_bps`: `39592.0`
- `no_trade_baseline_eur`: `0.0`
- `by_symbol`: `{'ADAEUR': {'trade_count': 76, 'net_pnl_eur': -68.806588}, 'BCHEUR': {'trade_count': 76, 'net_pnl_eur': -33.387116}, 'BTCZEUR': {'trade_count': 47, 'net_pnl_eur': -36.059423}, 'ETHZEUR': {'trade_count': 56, 'net_pnl_eur': -39.553207}, 'SOLEUR': {'trade_count': 82, 'net_pnl_eur': -53.841125}, 'XRPZEUR': {'trade_count': 67, 'net_pnl_eur': -60.533969}}`
- `by_period`: `{'2026-05-21': {'trade_count': 3, 'net_pnl_eur': -7.44}, '2026-05-22': {'trade_count': 14, 'net_pnl_eur': -33.22}, '2026-05-24': {'trade_count': 13, 'net_pnl_eur': -29.883189}, '2026-05-26': {'trade_count': 3, 'net_pnl_eur': -7.44}, '2026-05-29': {'trade_count': 1, 'net_pnl_eur': -2.524571}, '2026-05-30': {'trade_count': 2, 'net_pnl_eur': -4.703262}, '2026-05-31': {'trade_count': 12, 'net_pnl_eur': -29.131388}, '2026-06-07': {'trade_count': 14, 'net_pnl_eur': -14.540495}, '2026-06-08': {'trade_count': 15, 'net_pnl_eur': -16.683468}, '2026-06-09': {'trade_count': 28, 'net_pnl_eur': -91.805922}, '2026-06-10': {'trade_count': 4, 'net_pnl_eur': -12.913706}, '2026-06-12': {'trade_count': 8, 'net_pnl_eur': -15.267474}, '2026-06-13': {'trade_count': 3, 'net_pnl_eur': 2.990244}, '2026-06-14': {'trade_count': 44, 'net_pnl_eur': -45.917374}, '2026-06-15': {'trade_count': 20, 'net_pnl_eur': 21.199108}, '2026-06-16': {'trade_count': 13, 'net_pnl_eur': 20.801241}, '2026-06-17': {'trade_count': 12, 'net_pnl_eur': -33.399439}, '2026-06-20': {'trade_count': 3, 'net_pnl_eur': 7.879917}, '2026-06-21': {'trade_count': 7, 'net_pnl_eur': -17.452139}, '2026-06-22': {'trade_count': 15, 'net_pnl_eur': -11.815082}, '2026-06-26': {'trade_count': 1, 'net_pnl_eur': 4.208332}, '2026-06-27': {'trade_count': 7, 'net_pnl_eur': -17.508354}, '2026-06-28': {'trade_count': 15, 'net_pnl_eur': -47.944331}, '2026-06-29': {'trade_count': 3, 'net_pnl_eur': 12.345109}, '2026-06-30': {'trade_count': 19, 'net_pnl_eur': -57.053961}, '2026-07-01': {'trade_count': 10, 'net_pnl_eur': 11.807354}, '2026-07-02': {'trade_count': 17, 'net_pnl_eur': 44.449014}, '2026-07-03': {'trade_count': 24, 'net_pnl_eur': 81.541517}, '2026-07-04': {'trade_count': 33, 'net_pnl_eur': 59.965864}, '2026-07-05': {'trade_count': 17, 'net_pnl_eur': -1.088526}, '2026-07-06': {'trade_count': 16, 'net_pnl_eur': -40.825737}, '2026-07-07': {'trade_count': 2, 'net_pnl_eur': -6.043853}, '2026-07-08': {'trade_count': 6, 'net_pnl_eur': -14.766857}}`
- `adapter_decision`: `REJECT_FAST`
- `best_variant`: `1h_sma20_50_trend250_hold168_rr3`
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

Do not advance this hypothesis; keep it rejected/research-only until new data or a redesigned hypothesis exists.
