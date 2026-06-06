# Backtest Run - batch_strategy_validation_2026-06-06_full_TRXEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: grid research validation on TRXEUR

## Replay

- Events: 6841
- Signals: 22
- Fills: 22
- Rejected fills/signals: 0
- Closed trades: 11

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 989.90 |
| Net PnL | -10.098377 |
| Total return | -1.0098% |
| Max drawdown | 1.0098% |
| Profit factor | 0.001461 |
| Winrate | 9.090909% |
| Expectancy | -0.918034 |
| Fees | 3.520000 |
| Spread cost | 0.880000 |
| Slippage | 0.880000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -79.986980 | -7.9987% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -10.946137 | -1.0946% | Deterministic random long baseline, requested trades=11, executed=11. |

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

Decision: `keep_testing`
Registry proposal: `candidate`
Reason: `insufficient_closed_trades`
Live promotion allowed: `False`
