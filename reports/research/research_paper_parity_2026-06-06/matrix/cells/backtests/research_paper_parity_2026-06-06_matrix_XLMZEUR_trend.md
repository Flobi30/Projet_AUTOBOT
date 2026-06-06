# Backtest Run - research_paper_parity_2026-06-06_matrix_XLMZEUR_trend

Strategy: `trend_momentum`
Dataset: `autobot_state_db:XLMZEUR`
Hypothesis: trend research validation on XLMZEUR

## Replay

- Events: 16240
- Signals: 516
- Fills: 516
- Rejected fills/signals: 0
- Closed trades: 258

## Metrics

| Metric | Value |
| --- | ---: |
| Initial capital | 1000.00 |
| Final equity | 874.65 |
| Net PnL | -125.347928 |
| Total return | -12.5348% |
| Max drawdown | 12.5348% |
| Profit factor | 0.253206 |
| Winrate | 18.992248% |
| Expectancy | -0.485845 |
| Fees | 82.560000 |
| Spread cost | 20.640000 |
| Slippage | 20.640000 |

## Baselines

| Baseline | Net PnL | Return | Notes |
| --- | ---: | ---: | --- |
| no_trade | 0.000000 | 0.0000% |  |
| buy_and_hold | 187.195386 | 18.7195% | Equal capital allocation per symbol, net of configured costs. |
| random_signal_same_frequency | -563.581992 | -56.3582% | Deterministic random long baseline, requested trades=258, executed=258. |

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
