# Research Validation Matrix - batch_strategy_validation_2026-06-06_weekend

Mode: `backtest`
Cells: `6`
Success: `6`
Errors: `0`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Results

| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | grid | ok | keep_testing | insufficient_closed_trades | 1758 | 1 | -0.029871 | 0.320000 | 0.080000 | 0.080000 | -0.002987 | 0.000000 | 0.002987 |
| TRXEUR | mean_reversion | ok | keep_testing | insufficient_closed_trades | 1758 | 4 | -2.300088 | 1.280000 | 0.320000 | 0.320000 | -0.230009 | 0.000000 | 0.230009 |
| XLMZEUR | grid | ok | reject | negative_net_pnl | 4620 | 82 | -35.791094 | 26.240000 | 6.560000 | 6.560000 | -3.579109 | 0.257156 | 3.783717 |
| XLMZEUR | trend | ok | reject | negative_net_pnl | 4620 | 79 | -36.528168 | 25.280000 | 6.320000 | 6.320000 | -3.652817 | 0.270638 | 3.652817 |
| XLMZEUR | mean_reversion | ok | reject | negative_net_pnl | 4620 | 114 | -59.853978 | 36.480000 | 9.120000 | 9.120000 | -5.985398 | 0.129985 | 6.073068 |
| TRXEUR | trend | ok | keep_testing | insufficient_closed_trades | 1758 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  | 0.000000 |

## Safety

This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.
