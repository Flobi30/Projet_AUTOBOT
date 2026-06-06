# Backtest Run - batch_strategy_validation_2026-06-06_late_TRXEUR_grid

Strategy: `dynamic_grid`
Dataset: `autobot_state_db:TRXEUR`
Hypothesis: grid research validation on TRXEUR

## Replay

- Events: 2348
- Signals: 11
- Fills: 12
- Rejected fills/signals: 0
- Closed trades: 6

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 995.85 |
| Net PnL | -4.153712 |
| Total return | -0.4154% |
| Max drawdown | 0.4154% |
| Profit factor | 0.000000 |
| Winrate | 0.000000% |
| Expectancy | -0.692285 |
| Fees | 1.920000 |
| Spread cost | 0.480000 |
| Slippage | 0.480000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | -48.335559 | -4.8336% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -7.168948 | -0.7169% | Deterministic random long baseline, requested trades=6, executed=6. |

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
