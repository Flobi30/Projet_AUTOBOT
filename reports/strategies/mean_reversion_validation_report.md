# Strategy Validation Report: mean_reversion

Date: 2026-05-29

## Hypothesis

Bollinger/z-score snapback variants can capture temporary deviations in
range-like markets when trend strength is capped and expected snapback exceeds
transaction costs.

## Source Or Justification

`mean_reversion_shadow_lab` evaluates paper-only z-score variants. The legacy
`MeanReversionStrategy` class is explicitly guarded with `PRODUCTION_READY =
False`.

## Test Context

- Market: Kraken spot crypto EUR pairs
- Timeframe: rolling tick windows
- Period tested: shadow runtime only
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | Not standardized in this report |
| Gross return | Not standardized |
| Net return | Not standardized |
| Fees | Configurable per-side fee bps included in shadow lab |
| Slippage simulated | Configurable per-side slippage bps included in shadow lab |
| Max drawdown | Recorded in shadow state, not standardized here |
| Sharpe / Sortino | Not standardized |
| Profit factor | Recorded per variant, not accepted globally |
| Winrate | Recorded per variant, not accepted globally |
| Expectancy | Not standardized |

## Baseline Comparison

Required baselines are `no_trade`, dynamic grid on the same symbol and randomized
entries. The baseline bundle is missing.

## Performance By Regime

Expected regime is range/mean-reverting. Per-regime realized performance is not
yet standardized.

## Conclusion

Decision: continue shadow-only.

Status: `learning`.

Reason: the engine is not production-enabled and has not passed workflow gates.
