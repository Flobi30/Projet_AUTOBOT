# Research Validation Matrix - batch_strategy_validation_2026-06-06_late

Mode: `backtest`
Cells: `6`
Success: `6`
Errors: `0`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Results

| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | grid | ok | keep_testing | insufficient_closed_trades | 2348 | 6 | -4.153712 | 1.920000 | 0.480000 | 0.480000 | -0.415371 | 0.000000 | 0.415371 |
| TRXEUR | mean_reversion | ok | keep_testing | insufficient_closed_trades | 2348 | 21 | -11.893899 | 6.720000 | 1.680000 | 1.680000 | -1.189390 | 0.000000 | 1.189390 |
| XLMZEUR | trend | ok | reject | negative_net_pnl | 5168 | 58 | -27.737138 | 18.560000 | 4.640000 | 4.640000 | -2.773714 | 0.208417 | 2.773714 |
| XLMZEUR | grid | ok | reject | negative_net_pnl | 5168 | 56 | -27.920941 | 17.920000 | 4.480000 | 4.480000 | -2.792094 | 0.125443 | 2.805388 |
| XLMZEUR | mean_reversion | ok | reject | negative_net_pnl | 5168 | 150 | -63.671297 | 48.000000 | 12.000000 | 12.000000 | -6.367130 | 0.076688 | 6.367130 |
| TRXEUR | trend | ok | keep_testing | insufficient_closed_trades | 2348 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  | 0.000000 |

## Safety

This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.
