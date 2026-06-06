# Backtest Run - batch_strategy_validation_2026-06-06_early_TRXEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: trend research validation on TRXEUR

## Replay

- Events: 2331
- Signals: 0
- Fills: 0
- Rejected fills/signals: 0
- Closed trades: 0

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 1000.00 |
| Net PnL | 0.000000 |
| Total return | 0.0000% |
| Max drawdown | 0.0000% |
| Profit factor | N/A |
| Winrate | N/A% |
| Expectancy | N/A |
| Fees | 0.000000 |
| Spread cost | 0.000000 |
| Slippage | 0.000000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -25.983391 | -2.5983% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 0.000000 | 0.0000% | Not computed because the strategy produced no closed trades. |

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
