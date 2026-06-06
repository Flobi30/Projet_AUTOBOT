# Backtest Run - batch_strategy_validation_2026-06-06_late_XLMZEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: trend research validation on XLMZEUR

## Replay

- Events: 5168
- Signals: 116
- Fills: 116
- Rejected fills/signals: 0
- Closed trades: 58

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 972.26 |
| Net PnL | -27.737138 |
| Total return | -2.7737% |
| Max drawdown | 2.7737% |
| Profit factor | 0.208417 |
| Winrate | 15.517241% |
| Expectancy | -0.478227 |
| Fees | 18.560000 |
| Spread cost | 4.640000 |
| Slippage | 4.640000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -122.592146 | -12.2592% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -188.495967 | -18.8496% | Deterministic random long baseline, requested trades=58, executed=58. |

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
