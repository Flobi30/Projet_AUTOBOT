# Batch Strategy Validation - kraken_ohlcv_batch_5m_2026_06_07

Generated at: `2026-06-07T13:17:22.144670+00:00`
Data source: `csv`
Data path: `data\research\kraken_ohlcv_foundation_2026_06\kraken_ohlcv_foundation_2026_06_combined_5m.csv`
Strategies: `grid, trend, mean_reversion`
Symbols: `TRXEUR, XLMZEUR, BTCZEUR, ETHZEUR`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Window Summary

| Window | Cells | Success | Errors | Trades | Net PnL | Profitable Cells | Best | Worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| full | 12 | 12 | 0 | 171 | -96.582307 | 0 | TRXEUR/trend 0 | XLMZEUR/grid -14.368262585330704 |
| early | 12 | 12 | 0 | 74 | -44.899986 | 1 | XLMZEUR/mean_reversion 0.5450639778594863 | ETHZEUR/grid -9.516892780045929 |
| middle | 12 | 12 | 0 | 52 | -32.495300 | 0 | TRXEUR/trend 0 | ETHZEUR/grid -7.485753473665707 |
| late | 12 | 12 | 0 | 46 | -18.914030 | 2 | BTCZEUR/trend 0.5841231853003263 | XLMZEUR/grid -7.002523271128609 |
| weekend | 12 | 12 | 0 | 87 | -51.542888 | 1 | TRXEUR/grid 0.07396289524959404 | XLMZEUR/grid -12.70494151168176 |

## Status By Strategy

- `grid`: `research_only`
- `mean_reversion`: `research_only`
- `trend`: `research_only`

## Conclusion

No validation window was net positive after costs; keep strategies research-only.

## Safety

- Batch strategy validation is research-only.
- No runtime paper/live service is started.
- No paper or live order is created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
