# Backtest Run - batch_strategy_validation_2026-06-06_middle_XLMZEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: mean_reversion research validation on XLMZEUR

## Replay

- Events: 5292
- Signals: 291
- Fills: 292
- Rejected fills/signals: 0
- Closed trades: 146

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 919.45 |
| Net PnL | -80.546414 |
| Total return | -8.0546% |
| Max drawdown | 8.0546% |
| Profit factor | 0.090821 |
| Winrate | 23.972603% |
| Expectancy | -0.551688 |
| Fees | 46.720000 |
| Spread cost | 11.680000 |
| Slippage | 11.680000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -69.179702 | -6.9180% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -47.465291 | -4.7465% | Deterministic random long baseline, requested trades=146, executed=146. |

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
