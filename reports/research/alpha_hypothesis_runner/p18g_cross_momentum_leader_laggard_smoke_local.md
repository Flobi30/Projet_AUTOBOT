# P18C Alpha Hypothesis Runner - p18g_cross_momentum_leader_laggard_smoke_local

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.
- Commit: `9170d2222ff86ef7a9cc9ce3d80e069128d27448`.
- Hypothesis: `cross_momentum`.
- Runner mode: `smoke`.
- Final status: `REJECT_FAST`.
- Final decision: `STOPPED`.

## Architecture

Market data research store -> hypothesis registry -> autonomy policy -> sequential gates -> report.

## Gates

| Gate | Status | Passed | Stopped | Autonomy | Risk | Runtime s | Reasons |
|---|---|---:|---:|---|---|---:|---|
| `DATA_CHECK` | `KEEP_RESEARCH` | True | False | `AUTO_ALLOWED` | `neutral` | 0.222886 | data_ready |
| `FAST_NET_EDGE_TEST` | `REJECT_FAST` | False | True | `AUTO_ALLOWED` | `neutral` | 0.415444 | edge_net_not_positive, profit_factor_net_not_above_1, expectancy_net_not_positive |

## First Smoke Result

- `trade_count`: `53`
- `profit_factor_net`: `0.13846401196693212`
- `net_pnl_eur`: `-147.515495`
- `expectancy_net`: `-2.783311`
- `max_drawdown_eur`: `158.38698`
- `winrate_pct`: `28.301887`
- `total_cost_bps`: `5194.0`
- `no_trade_baseline_eur`: `0.0`
- `by_symbol`: `{'ADAEUR': {'trade_count': 21, 'net_pnl_eur': -92.699406}, 'SOLEUR': {'trade_count': 19, 'net_pnl_eur': -32.118547}, 'XRPZEUR': {'trade_count': 13, 'net_pnl_eur': -22.697542}}`
- `by_period`: `{'2026-05-11': {'trade_count': 2, 'net_pnl_eur': 3.164127}, '2026-05-12': {'trade_count': 2, 'net_pnl_eur': -9.143501}, '2026-05-13': {'trade_count': 2, 'net_pnl_eur': -5.593548}, '2026-05-14': {'trade_count': 2, 'net_pnl_eur': -4.87698}, '2026-05-15': {'trade_count': 4, 'net_pnl_eur': -7.160331}, '2026-05-16': {'trade_count': 3, 'net_pnl_eur': -14.141185}, '2026-05-17': {'trade_count': 1, 'net_pnl_eur': -0.224468}, '2026-05-18': {'trade_count': 1, 'net_pnl_eur': -2.00981}, '2026-05-20': {'trade_count': 1, 'net_pnl_eur': -0.905874}, '2026-05-21': {'trade_count': 2, 'net_pnl_eur': -1.521305}, '2026-05-22': {'trade_count': 2, 'net_pnl_eur': -1.337006}, '2026-05-23': {'trade_count': 1, 'net_pnl_eur': -4.413612}, '2026-05-24': {'trade_count': 2, 'net_pnl_eur': 6.537122}, '2026-05-25': {'trade_count': 3, 'net_pnl_eur': -1.993027}, '2026-05-29': {'trade_count': 2, 'net_pnl_eur': 0.815647}, '2026-05-31': {'trade_count': 4, 'net_pnl_eur': -3.584106}, '2026-06-01': {'trade_count': 1, 'net_pnl_eur': -1.76324}, '2026-06-02': {'trade_count': 1, 'net_pnl_eur': -6.888427}, '2026-06-03': {'trade_count': 2, 'net_pnl_eur': -11.484705}, '2026-06-04': {'trade_count': 3, 'net_pnl_eur': -30.935266}, '2026-06-05': {'trade_count': 4, 'net_pnl_eur': -47.544213}, '2026-06-06': {'trade_count': 3, 'net_pnl_eur': -8.860425}, '2026-06-07': {'trade_count': 3, 'net_pnl_eur': 5.114542}, '2026-06-08': {'trade_count': 2, 'net_pnl_eur': 1.234096}}`
- `concentration`: `{'top_positive_symbol': None, 'top_positive_pnl_share': 0.0}`
- `adapter_id`: `generic_cross_sectional_ohlcv_adapter`
- `mode_used`: `leader_laggard_momentum`
- `template_id`: `leader_laggard_momentum`
- `adapter_decision`: `REJECT_FAST`
- `variant_count`: `3`
- `primary_variant`: `lookback_bars24__min_correlation0.45__min_relative_strength_bps150`
- `availability`: `{'adapter_id': 'generic_cross_sectional_ohlcv_adapter', 'mode': 'leader_laggard_momentum', 'status': 'READY', 'available': True, 'symbols': ('ADAEUR', 'SOLEUR', 'XRPZEUR'), 'timeframes': ('15m', '1h', '5m'), 'start_at': '2026-05-09T08:00:00+00:00', 'end_at': '2026-06-08T08:25:00+00:00', 'row_count': 6489, 'duplicate_count': 0, 'selected_timeframe': '1h', 'reason': None}`

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
