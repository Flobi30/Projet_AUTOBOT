# Backtest Run - batch_strategy_validation_2026-06-06_weekend_XLMZEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: trend research validation on XLMZEUR

## Replay

- Events: 4620
- Signals: 158
- Fills: 158
- Rejected fills/signals: 0
- Closed trades: 79

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 963.47 |
| Net PnL | -36.528168 |
| Total return | -3.6528% |
| Max drawdown | 3.6528% |
| Profit factor | 0.270638 |
| Winrate | 18.987342% |
| Expectancy | -0.462382 |
| Fees | 25.280000 |
| Spread cost | 6.320000 |
| Slippage | 6.320000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -4.140684 | -0.4141% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -87.628872 | -8.7629% | Deterministic random long baseline, requested trades=79, executed=79. |

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
