# Strategy Validation Report: trend_momentum

Date: 2026-05-29

## Hypothesis

Trend-following variants can outperform grid behavior during directional,
expanding-volatility regimes when momentum exceeds fees, spread and slippage.

## Source Or Justification

`trend_shadow_lab` evaluates Donchian breakout and EMA momentum variants in
paper-only shadow mode.

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

Required baselines are `no_trade`, dynamic grid on the same symbol,
`buy_and_hold_symbol` and randomized entries. The baseline bundle is missing.

## Performance By Regime

Expected regime is trend/high momentum. Per-regime realized performance is not
yet standardized.

## Conclusion

Decision: continue shadow-only.

Status: `learning`.

Reason: no sufficient official paper, walk-forward or baseline evidence yet.
