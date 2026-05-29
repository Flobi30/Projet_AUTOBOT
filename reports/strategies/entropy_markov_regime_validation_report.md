# Strategy Validation Report: entropy_markov_regime

Date: 2026-05-29

## Hypothesis

A lightweight entropy plus Markov-state sensor can improve routing by detecting
range, trend, chaos, high-volatility and low-activity contexts.

## Source Or Justification

`regime_features.py` computes log returns, normalized Shannon entropy, a simple
Markov transition matrix and bounded score adjustment.

## Test Context

- Market: Kraken spot crypto EUR pairs
- Timeframe: rolling runtime price history
- Period tested: runtime observation
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | Not directly applicable |
| Gross return | Not directly applicable |
| Net return | Must be measured by score ablation |
| Fees | Downstream only |
| Slippage simulated | Downstream only |
| Max drawdown | Not directly applicable |
| Sharpe / Sortino | Not directly applicable |
| Profit factor | Must be compared with and without regime adjustment |
| Winrate | Must be compared with and without regime adjustment |
| Expectancy | Must be compared with and without regime adjustment |

## Baseline Comparison

Required baseline is opportunity scoring with `REGIME_SCORING_ENABLED=false`.
This ablation is not yet available.

## Performance By Regime

The module produces regimes, but there is not yet a realized performance table
by regime.

## Conclusion

Decision: keep as bounded context sensor.

Status: `learning`.

Reason: it should influence ranking lightly, never act as a standalone blocker
or price predictor.
