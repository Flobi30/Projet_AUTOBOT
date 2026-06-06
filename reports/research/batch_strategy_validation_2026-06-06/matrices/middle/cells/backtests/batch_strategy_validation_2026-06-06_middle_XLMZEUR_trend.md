# Backtest Run - batch_strategy_validation_2026-06-06_middle_XLMZEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: trend research validation on XLMZEUR

## Replay

- Events: 5292
- Signals: 158
- Fills: 158
- Rejected fills/signals: 0
- Closed trades: 79

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 961.97 |
| Net PnL | -38.029460 |
| Total return | -3.8029% |
| Max drawdown | 3.8029% |
| Profit factor | 0.197370 |
| Winrate | 17.721519% |
| Expectancy | -0.481386 |
| Fees | 25.280000 |
| Spread cost | 6.320000 |
| Slippage | 6.320000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -69.179702 | -6.9180% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 3.516897 | 0.3517% | Deterministic random long baseline, requested trades=79, executed=79. |

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
