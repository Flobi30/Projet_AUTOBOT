# Backtest Run - batch_strategy_validation_2026-06-06_full_XLMZEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: grid research validation on XLMZEUR

## Replay

- Events: 16240
- Signals: 492
- Fills: 492
- Rejected fills/signals: 0
- Closed trades: 246

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 890.39 |
| Net PnL | -109.605392 |
| Total return | -10.9605% |
| Max drawdown | 10.9859% |
| Profit factor | 0.223828 |
| Winrate | 67.479675% |
| Expectancy | -0.445550 |
| Fees | 78.720000 |
| Spread cost | 19.680000 |
| Slippage | 19.680000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 187.195386 | 18.7195% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -269.530512 | -26.9531% | Deterministic random long baseline, requested trades=246, executed=246. |

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
