# Backtest Run - batch_strategy_validation_2026-06-06_weekend_XLMZEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: mean_reversion research validation on XLMZEUR

## Replay

- Events: 4620
- Signals: 228
- Fills: 228
- Rejected fills/signals: 0
- Closed trades: 114

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 940.15 |
| Net PnL | -59.853978 |
| Total return | -5.9854% |
| Max drawdown | 6.0731% |
| Profit factor | 0.129985 |
| Winrate | 28.070175% |
| Expectancy | -0.525035 |
| Fees | 36.480000 |
| Spread cost | 9.120000 |
| Slippage | 9.120000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -4.140684 | -0.4141% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -115.860542 | -11.5861% | Deterministic random long baseline, requested trades=114, executed=114. |

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
