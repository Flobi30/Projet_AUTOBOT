# VPS Validation Matrix Summary - 2026-06-01

Source: local read-only copy of `/opt/Projet_AUTOBOT/data/autobot_state.db`
from the VPS.

Dataset window: `2026-05-27T20:25:09Z` to `2026-06-01T11:55:57Z`.

Run id: `vps_2026_06_01_top14`

Mode: `backtest`

Scope:

- 14 symbols: `TRXEUR`, `SOLEUR`, `ETHZEUR`, `BTCZEUR`, `LTCZEUR`,
  `XLMZEUR`, `XRPZEUR`, `ADAEUR`, `LINKEUR`, `DOTEUR`, `BCHEUR`,
  `ATOMEUR`, `AVAXEUR`, `AAVEEUR`.
- 3 strategy families: `grid`, `trend`, `mean_reversion`.
- 42 matrix cells.
- 42 successful cells.
- 0 runtime errors.
- Costs included through the configured research cost model.

## Registry Recommendations

| Strategy | Registry ID | Current | Recommended | Reason | Symbols Passing | Closed Trades | Net PnL | Best PF | Worst DD | Live Allowed |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| grid | dynamic_grid | candidate | rejected | non_positive_aggregate_net_pnl | 0/14 | 391 | -190.493353 | 0.305394 | 7.191241 | false |
| mean_reversion | mean_reversion | learning | rejected | non_positive_aggregate_net_pnl | 0/14 | 706 | -353.386757 | 0.283037 | 4.589784 | false |
| trend | trend_momentum | learning | rejected | non_positive_aggregate_net_pnl | 0/14 | 221 | -115.803564 | 0.540026 | 6.801713 | false |

## Interpretation

This is a conservative research backtest over runtime price samples, not a live
or official paper PnL report. It should not be used alone to delete a strategy,
but it is strong evidence that the current default research configurations do
not have a positive expectancy after costs on the captured VPS sample.

Key reading:

- No strategy family passed on any of the 14 symbols.
- The best observed profit factors are still far below 1.0.
- The losses are not isolated to one pair; all three strategy families are
  negative in aggregate.
- `XLMZEUR` is especially destructive across all three families in this sample.
- `trend` trades less often, but still does not overcome costs.
- `mean_reversion` produces the largest trade count and the worst aggregate
  net PnL, which suggests it needs stricter entry quality or a different regime
  gate before any official promotion.

## Limitations

- The data comes from `market_price_samples`, not full OHLCV candles with order
  book depth.
- Bid/ask spread and queue position are simulated, not measured from depth.
- This is not yet walk-forward validation.
- This is not a parameter search.
- This does not mutate `strategy_hypotheses.json`.
- This does not permit live trading.

## Recommended Next Action

Do not lower thresholds to force trades.

Instead:

1. Keep all three strategy families below live/paper-promotion gates.
2. Run walk-forward validation on richer historical OHLCV/depth data.
3. Add per-strategy diagnostics for why entries are losing after costs:
   entry timing, TP/SL distance, hold duration, spread drag, and regime at
   entry.
4. Compare official paper ledger decisions against this backtest matrix to find
   whether the production router is executing a different setup than the
   research harness.
5. Treat any future strategy improvement as untrusted until it beats no-trade,
   buy-and-hold, and random-same-frequency baselines after fees/slippage.
