# Research Validation Matrix - batch_strategy_validation_2026-06-06_middle

Mode: `backtest`
Cells: `6`
Success: `6`
Errors: `0`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Results

| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | grid | ok | keep_testing | insufficient_closed_trades | 2162 | 2 | -1.461552 | 0.640000 | 0.160000 | 0.160000 | -0.146155 | 0.000000 | 0.146155 |
| TRXEUR | mean_reversion | ok | keep_testing | insufficient_closed_trades | 2162 | 4 | -2.043771 | 1.280000 | 0.320000 | 0.320000 | -0.204377 | 0.000000 | 0.204377 |
| XLMZEUR | trend | ok | reject | negative_net_pnl | 5292 | 79 | -38.029460 | 25.280000 | 6.320000 | 6.320000 | -3.802946 | 0.197370 | 3.802946 |
| XLMZEUR | grid | ok | reject | negative_net_pnl | 5292 | 75 | -43.570238 | 24.000000 | 6.000000 | 6.000000 | -4.357024 | 0.141222 | 4.357024 |
| XLMZEUR | mean_reversion | ok | reject | negative_net_pnl | 5292 | 146 | -80.546414 | 46.720000 | 11.680000 | 11.680000 | -8.054641 | 0.090821 | 8.054641 |
| TRXEUR | trend | ok | keep_testing | insufficient_closed_trades | 2162 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  | 0.000000 |

## Safety

This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.
