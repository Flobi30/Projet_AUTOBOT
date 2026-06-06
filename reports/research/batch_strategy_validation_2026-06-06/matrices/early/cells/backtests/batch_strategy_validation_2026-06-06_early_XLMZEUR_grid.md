# Backtest Run - batch_strategy_validation_2026-06-06_early_XLMZEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: grid research validation on XLMZEUR

## Replay

- Events: 5780
- Signals: 233
- Fills: 234
- Rejected fills/signals: 0
- Closed trades: 117

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 959.38 |
| Net PnL | -40.616423 |
| Total return | -4.0616% |
| Max drawdown | 4.1084% |
| Profit factor | 0.326311 |
| Winrate | 71.794872% |
| Expectancy | -0.347149 |
| Fees | 37.440000 |
| Spread cost | 9.360000 |
| Slippage | 9.360000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 427.985761 | 42.7986% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 1179.451991 | 117.9452% | Deterministic random long baseline, requested trades=117, executed=117. |

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
