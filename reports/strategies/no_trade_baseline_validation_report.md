# Strategy Validation Report: no_trade_baseline

Date: 2026-05-29

## Hypothesis

Abstaining is a valid safety baseline and should beat negative-expectancy
trading after costs.

## Source Or Justification

The strategy router includes `no_trade` as a safety choice when evidence is
weak, all engines are weak, or the sample is insufficient.

## Test Context

- Market: all monitored AUTOBOT markets
- Timeframe: all runtime horizons
- Period tested: continuous safety baseline
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | 0 |
| Gross return | 0 |
| Net return | 0 |
| Fees | 0 |
| Slippage simulated | 0 |
| Max drawdown | 0 |
| Sharpe / Sortino | Not meaningful |
| Profit factor | Not meaningful |
| Winrate | Not meaningful |
| Expectancy | 0 |

## Baseline Comparison

This is the baseline. It must be beaten after costs before a strategy is
promoted.

## Performance By Regime

Applies to weak-signal, high-cost, uncertain or unsafe regimes.

## Conclusion

Decision: keep.

Status: `paper_validated`.

Reason: capital preservation is required while official paper evidence remains
weak.
