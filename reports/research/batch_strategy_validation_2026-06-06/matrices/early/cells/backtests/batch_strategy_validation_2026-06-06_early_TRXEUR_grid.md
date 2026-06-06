# Backtest Run - batch_strategy_validation_2026-06-06_early_TRXEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: grid research validation on TRXEUR

## Replay

- Events: 2331
- Signals: 8
- Fills: 8
- Rejected fills/signals: 0
- Closed trades: 4

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 997.63 |
| Net PnL | -2.366391 |
| Total return | -0.2366% |
| Max drawdown | 0.2366% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.591598 |
| Fees | 1.280000 |
| Spread cost | 0.320000 |
| Slippage | 0.320000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -25.983391 | -2.5983% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -4.020741 | -0.4021% | Deterministic random long baseline, requested trades=4, executed=4. |

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
