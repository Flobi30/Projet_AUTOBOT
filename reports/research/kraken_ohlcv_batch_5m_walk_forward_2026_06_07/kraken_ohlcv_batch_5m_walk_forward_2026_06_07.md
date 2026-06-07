# Batch Strategy Validation - kraken_ohlcv_batch_5m_walk_forward_2026_06_07

Generated at: `2026-06-07T13:18:04.309418+00:00`
Data source: `csv`
Data path: `data\research\kraken_ohlcv_foundation_2026_06\kraken_ohlcv_foundation_2026_06_combined_5m.csv`
Strategies: `grid, trend, mean_reversion`
Symbols: `TRXEUR, XLMZEUR, BTCZEUR, ETHZEUR`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Window Summary

| Window | Cells | Success | Errors | Trades | Net PnL | Profitable Cells | Best | Worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| full | 12 | 12 | 0 | 98 | -53.533812 | 0 | TRXEUR/trend 0 | XLMZEUR/grid -18.082681177151315 |
| early | 12 | 12 | 0 | 0 | 0.000000 | 0 | ETHZEUR/mean_reversion 0 | TRXEUR/grid 0 |
| middle | 12 | 12 | 0 | 0 | 0.000000 | 0 | ETHZEUR/mean_reversion 0 | TRXEUR/grid 0 |
| late | 12 | 12 | 0 | 0 | 0.000000 | 0 | ETHZEUR/mean_reversion 0 | TRXEUR/grid 0 |
| weekend | 12 | 12 | 0 | 33 | -14.491930 | 5 | BTCZEUR/trend 0.7189760667089975 | XLMZEUR/grid -8.132273905200574 |

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
