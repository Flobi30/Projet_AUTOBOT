# Backtest Run - batch_strategy_validation_2026-06-06_early_XLMZEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: trend research validation on XLMZEUR

## Replay

- Events: 5780
- Signals: 242
- Fills: 242
- Rejected fills/signals: 0
- Closed trades: 121

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 940.42 |
| Net PnL | -59.581330 |
| Total return | -5.9581% |
| Max drawdown | 6.0481% |
| Profit factor | 0.302546 |
| Winrate | 21.487603% |
| Expectancy | -0.492408 |
| Fees | 38.720000 |
| Spread cost | 9.680000 |
| Slippage | 9.680000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 427.985761 | 42.7986% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | 1198.038282 | 119.8038% | Deterministic random long baseline, requested trades=121, executed=121. |

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
