# Backtest Run - batch_strategy_validation_2026-06-06_late_XLMZEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: grid research validation on XLMZEUR

## Replay

- Events: 5168
- Signals: 112
- Fills: 112
- Rejected fills/signals: 0
- Closed trades: 56

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 972.08 |
| Net PnL | -27.920941 |
| Total return | -2.7921% |
| Max drawdown | 2.8054% |
| Profit factor | 0.125443 |
| Winrate | 57.142857% |
| Expectancy | -0.498588 |
| Fees | 17.920000 |
| Spread cost | 4.480000 |
| Slippage | 4.480000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -122.592146 | -12.2592% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -154.241694 | -15.4242% | Deterministic random long baseline, requested trades=56, executed=56. |

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
