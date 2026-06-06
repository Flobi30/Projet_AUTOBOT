# Backtest Run - research_paper_parity_2026-06-06_matrix_XLMZEUR_mean_reversion

Strategy: `mean_reversion`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: mean_reversion research validation on XLMZEUR

## Replay

- Events: 16240
- Signals: 840
- Fills: 840
- Rejected fills/signals: 0
- Closed trades: 420

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 812.31 |
| Net PnL | -187.692667 |
| Total return | -18.7693% |
| Max drawdown | 18.8128% |
| Profit factor | 0.144786 |
| Winrate | 28.333333% |
| Expectancy | -0.446887 |
| Fees | 134.400000 |
| Spread cost | 33.600000 |
| Slippage | 33.600000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 187.195386 | 18.7195% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -342.629958 | -34.2630% | Deterministic random long baseline, requested trades=420, executed=420. |

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
