# Strategy Validation Report: dynamic_grid

Date: 2026-05-29

## Hypothesis

A cost-aware adaptive grid can capture repeated mean-reverting moves on liquid
EUR crypto pairs when spread is tight, volatility is sufficient and trend risk
is controlled.

## Source Or Justification

Existing AUTOBOT grid runtime plus `setup_shadow_lab` virtual variants.

## Test Context

- Market: Kraken spot crypto EUR pairs
- Timeframe: runtime tick stream and rolling shadow samples
- Period tested: ongoing paper runtime, not an immutable backtest id yet
- Last backtest id: none

## Metrics

| Metric | Value |
| --- | --- |
| Trades | 555 official paper closed trades observed in current registry snapshot |
| Gross return | Not standardized in this report |
| Net return | -21.3979 EUR aggregate official paper PnL |
| Fees | Included in official ledger where available |
| Slippage simulated | Partially tracked in official ledger; fixed bps in shadow lab |
| Max drawdown | Not standardized in this report |
| Sharpe / Sortino | Not standardized in this report |
| Profit factor | Positive on TRXEUR only in snapshot; aggregate not accepted |
| Winrate | TRXEUR 52.54 percent in snapshot |
| Expectancy | Not standardized in this report |

## Baseline Comparison

Required baselines are `no_trade`, `buy_and_hold_symbol`,
`random_entry_same_frequency` and previous static grid config. These are not yet
available in one standardized event-driven report, so the strategy cannot move
to `backtest_passed`.

## Performance By Regime

Regime features exist, but performance by regime is not yet standardized.

## Conclusion

Decision: continue test, do not live.

Status: `candidate`.

Reason: the official paper ledger is negative in aggregate and the current
evidence is not a full walk-forward event-driven backtest.
