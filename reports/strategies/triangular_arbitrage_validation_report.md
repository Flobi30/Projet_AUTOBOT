# Strategy Validation Report: triangular_arbitrage

Date: 2026-05-29

## Hypothesis

Triangular cross-rate inconsistencies could produce net profit after three legs
of fees if depth, latency and fill risk are modeled.

## Source Or Justification

`strategies/arbitrage.py` contains a prototype detector with per-leg fees.

## Test Context

- Market: crypto cross pairs
- Timeframe: prototype calculation only
- Period tested: not part of official paper stack
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | 0 official AUTOBOT trades |
| Gross return | Not validated |
| Net return | Not validated |
| Fees | Prototype applies fee percentage |
| Slippage simulated | Not production-grade |
| Max drawdown | Not validated |
| Sharpe / Sortino | Not validated |
| Profit factor | Not validated |
| Winrate | Not validated |
| Expectancy | Not validated |

## Baseline Comparison

No valid baseline with synchronized depth and multi-leg execution exists.

## Performance By Regime

Not evaluated.

## Conclusion

Decision: do not execute.

Status: `retired_from_execution`.

Reason: multi-leg depth, latency and partial-fill risk are not modeled enough
for paper or live routing.
