# Backtest Run - research_paper_parity_2026-06-06_matrix_TRXEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: mean_reversion research validation on TRXEUR

## Replay

- Events: 6841
- Signals: 76
- Fills: 76
- Rejected fills/signals: 0
- Closed trades: 38

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 975.82 |
| Net PnL | -24.182263 |
| Total return | -2.4182% |
| Max drawdown | 2.4182% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.636375 |
| Fees | 12.160000 |
| Spread cost | 3.040000 |
| Slippage | 3.040000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -79.986980 | -7.9987% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -66.613704 | -6.6614% | Deterministic random long baseline, requested trades=38, executed=38. |

## Cost Assumptions

| Parameter | Value |
| --- | ---: |
| fallback_spread_bps | 8.000000 |
| latency_buffer_bps | 1.000000 |
| maker_fee_bps | 10.000000 |
| max_liquidity_participation | 0.050000 |
| max_spread_bps | 80.000000 |
| min_notional_eur | 5.000000 |
| slippage_bps | 4.000000 |
| taker_fee_bps | 16.000000 |

## Decision

Decision: `reject`
Registry proposal: `rejected`
Reason: `negative_net_pnl`
Live promotion allowed: `False`
