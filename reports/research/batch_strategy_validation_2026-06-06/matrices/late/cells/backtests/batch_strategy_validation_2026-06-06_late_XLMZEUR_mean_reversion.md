# Backtest Run - batch_strategy_validation_2026-06-06_late_XLMZEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: mean_reversion research validation on XLMZEUR

## Replay

- Events: 5168
- Signals: 300
- Fills: 300
- Rejected fills/signals: 0
- Closed trades: 150

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 936.33 |
| Net PnL | -63.671297 |
| Total return | -6.3671% |
| Max drawdown | 6.3671% |
| Profit factor | 0.076688 |
| Winrate | 20.000000% |
| Expectancy | -0.424475 |
| Fees | 48.000000 |
| Spread cost | 12.000000 |
| Slippage | 12.000000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -122.592146 | -12.2592% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -509.273851 | -50.9274% | Deterministic random long baseline, requested trades=150, executed=150. |

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
