# Backtest Run - batch_strategy_validation_2026-06-06_weekend_XLMZEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: grid research validation on XLMZEUR

## Replay

- Events: 4620
- Signals: 163
- Fills: 164
- Rejected fills/signals: 0
- Closed trades: 82

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 964.21 |
| Net PnL | -35.791094 |
| Total return | -3.5791% |
| Max drawdown | 3.7837% |
| Profit factor | 0.257156 |
| Winrate | 70.731707% |
| Expectancy | -0.436477 |
| Fees | 26.240000 |
| Spread cost | 6.560000 |
| Slippage | 6.560000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -4.140684 | -0.4141% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -79.966867 | -7.9967% | Deterministic random long baseline, requested trades=82, executed=82. |

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
