# Backtest Run - batch_strategy_validation_2026-06-06_weekend_TRXEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: mean_reversion research validation on TRXEUR

## Replay

- Events: 1758
- Signals: 8
- Fills: 8
- Rejected fills/signals: 0
- Closed trades: 4

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 997.70 |
| Net PnL | -2.300088 |
| Total return | -0.2300% |
| Max drawdown | 0.2300% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.575022 |
| Fees | 1.280000 |
| Spread cost | 0.320000 |
| Slippage | 0.320000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 16.634119 | 1.6634% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 2.341546 | 0.2342% | Deterministic random long baseline, requested trades=4, executed=4. |

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
