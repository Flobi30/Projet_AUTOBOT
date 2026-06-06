# Backtest Run - batch_strategy_validation_2026-06-06_middle_XLMZEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: grid research validation on XLMZEUR

## Replay

- Events: 5292
- Signals: 149
- Fills: 150
- Rejected fills/signals: 0
- Closed trades: 75

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 956.43 |
| Net PnL | -43.570238 |
| Total return | -4.3570% |
| Max drawdown | 4.3570% |
| Profit factor | 0.141222 |
| Winrate | 64.000000% |
| Expectancy | -0.580937 |
| Fees | 24.000000 |
| Spread cost | 6.000000 |
| Slippage | 6.000000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -69.179702 | -6.9180% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -44.918274 | -4.4918% | Deterministic random long baseline, requested trades=75, executed=75. |

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
