# Backtest Run - batch_strategy_validation_2026-06-06_early_XLMZEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: mean_reversion research validation on XLMZEUR

## Replay

- Events: 5780
- Signals: 245
- Fills: 246
- Rejected fills/signals: 0
- Closed trades: 123

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 955.60 |
| Net PnL | -44.398054 |
| Total return | -4.4398% |
| Max drawdown | 4.4911% |
| Profit factor | 0.288812 |
| Winrate | 43.089431% |
| Expectancy | -0.360960 |
| Fees | 39.360000 |
| Spread cost | 9.840000 |
| Slippage | 9.840000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 427.985761 | 42.7986% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 1111.353730 | 111.1354% | Deterministic random long baseline, requested trades=123, executed=123. |

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
