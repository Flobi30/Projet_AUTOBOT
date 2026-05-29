# Strategy Validation Report: opportunity_scoring

Date: 2026-05-29

## Hypothesis

Combining gross edge, cost, ATR, spread, liquidity, stability, regime and pair
health can improve opportunity ranking before risk and execution.

## Source Or Justification

`opportunity_scoring.py` is an active runtime scoring and allocation guard. It
does not generate alpha by itself.

## Test Context

- Market: Kraken spot crypto EUR pairs
- Timeframe: latest signal/decision context
- Period tested: runtime paper observation
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | Not directly applicable |
| Gross return | Not directly applicable |
| Net return | Must be measured by ablation |
| Fees | Consumed through edge context |
| Slippage simulated | Consumed through edge context |
| Max drawdown | Not directly applicable |
| Sharpe / Sortino | Not directly applicable |
| Profit factor | Must be compared with and without scorer |
| Winrate | Must be compared with and without scorer |
| Expectancy | Must be compared with and without scorer |

## Baseline Comparison

Required baseline is the same strategy flow without opportunity score, plus
no-trade and random top-k selection. This ablation is not yet available.

## Performance By Regime

Regime context is included, but realized incremental value is not yet proven.

## Conclusion

Decision: keep as guard and measure incremental value.

Status: `candidate`.

Reason: useful as a guard, but not a standalone validated strategy.
