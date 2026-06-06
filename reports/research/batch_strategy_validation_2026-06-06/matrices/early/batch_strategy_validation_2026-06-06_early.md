# Research Validation Matrix - batch_strategy_validation_2026-06-06_early

Mode: `backtest`
Cells: `6`
Success: `6`
Errors: `0`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Results

| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | grid | ok | keep_testing | insufficient_closed_trades | 2331 | 4 | -2.366391 | 1.280000 | 0.320000 | 0.320000 | -0.236639 | 0.000000 | 0.236639 |
| TRXEUR | mean_reversion | ok | keep_testing | insufficient_closed_trades | 2331 | 13 | -10.244593 | 4.160000 | 1.040000 | 1.040000 | -1.024459 | 0.000000 | 1.024459 |
| XLMZEUR | grid | ok | reject | negative_net_pnl | 5780 | 117 | -40.616423 | 37.440000 | 9.360000 | 9.360000 | -4.061642 | 0.326311 | 4.108375 |
| XLMZEUR | mean_reversion | ok | reject | negative_net_pnl | 5780 | 123 | -44.398054 | 39.360000 | 9.840000 | 9.840000 | -4.439805 | 0.288812 | 4.491053 |
| XLMZEUR | trend | ok | reject | negative_net_pnl | 5780 | 121 | -59.581330 | 38.720000 | 9.680000 | 9.680000 | -5.958133 | 0.302546 | 6.048091 |
| TRXEUR | trend | ok | keep_testing | insufficient_closed_trades | 2331 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  | 0.000000 |

## Safety

This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.
