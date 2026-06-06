# Backtest Run - batch_strategy_validation_2026-06-06_early_TRXEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: mean_reversion research validation on TRXEUR

## Replay

- Events: 2331
- Signals: 26
- Fills: 26
- Rejected fills/signals: 0
- Closed trades: 13

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 989.76 |
| Net PnL | -10.244593 |
| Total return | -1.0245% |
| Max drawdown | 1.0245% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.788046 |
| Fees | 4.160000 |
| Spread cost | 1.040000 |
| Slippage | 1.040000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -25.983391 | -2.5983% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -10.109835 | -1.0110% | Deterministic random long baseline, requested trades=13, executed=13. |

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
