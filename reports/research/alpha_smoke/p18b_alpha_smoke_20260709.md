# P18B Alpha Smoke Runner - p18b_alpha_smoke_20260709

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no UI change, no sizing/leverage change.
- Commit: `7748bf109cb34cc376398578a38b9bc6cd816fee`.

## Data Availability

| Hypothesis | Status | Rows | Symbols | Timeframes | Period | Duplicates | Gaps | Cost | Reason |
|---|---|---:|---:|---|---|---:|---:|---|---|
| `volatility_breakout_high_conviction` | `READY` | 68478 | 6 | 15m, 1h, 5m | 2026-05-16T16:00:00+00:00 -> 2026-07-09T00:15:00+00:00 | 275439 | 0 | L/M bounded smoke |  |
| `long_timeframe_adaptive_trend` | `READY` | 68478 | 6 | 15m, 1h, 5m | 2026-05-16T16:00:00+00:00 -> 2026-07-09T00:15:00+00:00 | 275439 | 0 | L/M bounded smoke |  |
| `funding_basis` | `MISSING_DATA` | 68478 | 6 | 15m, 1h, 5m | 2026-05-16T16:00:00+00:00 -> 2026-07-09T00:15:00+00:00 | 275439 | 0 | L/M bounded smoke | requires non-OHLCV derivatives/event data not available in this smoke runner |
| `liquidation_cascade` | `MISSING_DATA` | 68478 | 6 | 15m, 1h, 5m | 2026-05-16T16:00:00+00:00 -> 2026-07-09T00:15:00+00:00 | 275439 | 0 | L/M bounded smoke | requires non-OHLCV derivatives/event data not available in this smoke runner |

## Smoke Results

### volatility_breakout_high_conviction

- decision: `KEEP_RESEARCH`
- variants: `3`
- best_variant: `fixed_tp_sl__min500bps__rr2__hold72h`
- trade_count: `206`
- PF net: `1.02477`
- expectancy net: `0.0533626`
- net PnL EUR: `10.9927`
- max drawdown EUR: `119.8`
- win rate: `36.8932`
- no_trade_baseline_eur: `0.0`
- elapsed_seconds: `6.6819`

Reasons:
- positive_smoke_requires_walk_forward_before_shadow
- no_shadow_or_paper_allowed

| Symbol | Trades | Net PnL EUR |
|---|---:|---:|
| `BCHEUR` | 51 | 93.7684 |
| `ADAEUR` | 59 | 16.8601 |
| `ETHZEUR` | 23 | -2.76154 |
| `XRPZEUR` | 30 | -32.4365 |
| `SOLEUR` | 43 | -64.4377 |

| Period | Trades | Net PnL EUR |
|---|---:|---:|

### long_timeframe_adaptive_trend

- decision: `REJECT_FAST`
- variants: `3`
- best_variant: `1h_sma20_50_trend250_hold168_rr3`
- trade_count: `404`
- PF net: `0.599202`
- expectancy net: `-0.723221`
- net PnL EUR: `-292.181`
- max drawdown EUR: `294.093`
- win rate: `34.4059`
- no_trade_baseline_eur: `0.0`
- elapsed_seconds: `0.429107`

Reasons:
- edge_net_not_positive
- profit_factor_net_not_above_1
- expectancy_net_not_positive

| Symbol | Trades | Net PnL EUR |
|---|---:|---:|
| `BCHEUR` | 76 | -33.3871 |
| `BTCZEUR` | 47 | -36.0594 |
| `ETHZEUR` | 56 | -39.5532 |
| `SOLEUR` | 82 | -53.8411 |
| `XRPZEUR` | 67 | -60.534 |
| `ADAEUR` | 76 | -68.8066 |

| Period | Trades | Net PnL EUR |
|---|---:|---:|
| `2026-05-21` | 3 | -7.44 |
| `2026-05-22` | 14 | -33.22 |
| `2026-05-24` | 13 | -29.8832 |
| `2026-05-26` | 3 | -7.44 |
| `2026-05-29` | 1 | -2.52457 |
| `2026-05-30` | 2 | -4.70326 |
| `2026-05-31` | 12 | -29.1314 |
| `2026-06-07` | 14 | -14.5405 |
| `2026-06-08` | 15 | -16.6835 |
| `2026-06-09` | 28 | -91.8059 |
| `2026-06-10` | 4 | -12.9137 |
| `2026-06-12` | 8 | -15.2675 |
| `2026-06-13` | 3 | 2.99024 |
| `2026-06-14` | 44 | -45.9174 |
| `2026-06-15` | 20 | 21.1991 |
| `2026-06-16` | 13 | 20.8012 |
| `2026-06-17` | 12 | -33.3994 |
| `2026-06-20` | 3 | 7.87992 |
| `2026-06-21` | 7 | -17.4521 |
| `2026-06-22` | 15 | -11.8151 |
| `2026-06-26` | 1 | 4.20833 |
| `2026-06-27` | 7 | -17.5084 |
| `2026-06-28` | 15 | -47.9443 |
| `2026-06-29` | 3 | 12.3451 |
| `2026-06-30` | 19 | -57.054 |
| `2026-07-01` | 10 | 11.8074 |
| `2026-07-02` | 17 | 44.449 |
| `2026-07-03` | 24 | 81.5415 |
| `2026-07-04` | 33 | 59.9659 |
| `2026-07-05` | 17 | -1.08853 |
| `2026-07-06` | 16 | -40.8257 |
| `2026-07-07` | 2 | -6.04385 |
| `2026-07-08` | 6 | -14.7669 |

## Hypotheses Not Tested

| Hypothesis | Status | Reason |
|---|---|---|
| `funding_basis` | `MISSING_DATA` | requires derivatives funding/liquidation data not collected in the current Kraken Spot OHLCV research store |
| `liquidation_cascade` | `MISSING_DATA` | requires derivatives funding/liquidation data not collected in the current Kraken Spot OHLCV research store |

## Safety

- Read-only Alpha Hypothesis Lab smoke runner.
- No runtime trading component is imported or called.
- No order, paper capital, live flag, sizing, leverage, dashboard, or promotion path is touched.
- Grid remains archived/no-go; trend and mean reversion remain benchmarks only.
- paper_capital_allowed: `False`
- live_promotion_allowed: `False`
- promotable: `False`

## Recommendation P18C

Continue research-only validation for volatility_breakout_high_conviction with walk-forward before any shadow consideration.
