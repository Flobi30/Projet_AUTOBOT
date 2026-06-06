# Batch Strategy Validation - batch_strategy_validation_2026-06-06

Generated at: `2026-06-06T16:49:29.564474+00:00`
Strategies: `grid, trend, mean_reversion`
Symbols: `TRXEUR, XLMZEUR`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Window Summary

| Window | Cells | Success | Errors | Trades | Net PnL | Profitable Cells | Best | Worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| full | 6 | 6 | 0 | 973 | -456.926628 | 0 | TRXEUR/trend 0 | XLMZEUR/mean_reversion -187.69266742826935 |
| early | 6 | 6 | 0 | 378 | -157.206791 | 0 | TRXEUR/trend 0 | XLMZEUR/trend -59.581330082469556 |
| middle | 6 | 6 | 0 | 306 | -165.651435 | 0 | TRXEUR/trend 0 | XLMZEUR/mean_reversion -80.54641374532743 |
| late | 6 | 6 | 0 | 291 | -135.376986 | 0 | TRXEUR/trend 0 | XLMZEUR/mean_reversion -63.67129705314736 |
| weekend | 6 | 6 | 0 | 280 | -134.503199 | 0 | TRXEUR/trend 0 | XLMZEUR/mean_reversion -59.853977558865864 |

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
