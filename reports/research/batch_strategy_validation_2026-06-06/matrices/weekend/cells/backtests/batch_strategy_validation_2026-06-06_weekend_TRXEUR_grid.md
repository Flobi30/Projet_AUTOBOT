# Backtest Run - batch_strategy_validation_2026-06-06_weekend_TRXEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: grid research validation on TRXEUR

## Replay

- Events: 1758
- Signals: 2
- Fills: 2
- Rejected fills/signals: 0
- Closed trades: 1

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 999.97 |
| Net PnL | -0.029871 |
| Total return | -0.0030% |
| Max drawdown | 0.0030% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.029871 |
| Fees | 0.320000 |
| Spread cost | 0.080000 |
| Slippage | 0.080000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 16.634119 | 1.6634% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 1.223628 | 0.1224% | Deterministic random long baseline, requested trades=1, executed=1. |

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
