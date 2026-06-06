# Backtest Run - batch_strategy_validation_2026-06-06_middle_TRXEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: mean_reversion research validation on TRXEUR

## Replay

- Events: 2162
- Signals: 8
- Fills: 8
- Rejected fills/signals: 0
- Closed trades: 4

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 997.96 |
| Net PnL | -2.043771 |
| Total return | -0.2044% |
| Max drawdown | 0.2044% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.510943 |
| Fees | 1.280000 |
| Spread cost | 0.320000 |
| Slippage | 0.320000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -17.727011 | -1.7727% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -6.229671 | -0.6230% | Deterministic random long baseline, requested trades=4, executed=4. |

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
