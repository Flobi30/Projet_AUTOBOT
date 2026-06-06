# Research Validation Matrix - batch_strategy_validation_2026-06-06_full

Mode: `backtest`
Cells: `6`
Success: `6`
Errors: `0`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Results

| Symbol | Strategy | Status | Decision | Reason | Bars | Trades | Net PnL | Fees | Spread | Slippage | Return | PF | Max DD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | grid | ok | keep_testing | insufficient_closed_trades | 6841 | 11 | -10.098377 | 3.520000 | 0.880000 | 0.880000 | -1.009838 | 0.001461 | 1.009838 |
| TRXEUR | mean_reversion | ok | reject | negative_net_pnl | 6841 | 38 | -24.182263 | 12.160000 | 3.040000 | 3.040000 | -2.418226 | 0.000000 | 2.418226 |
| XLMZEUR | grid | ok | reject | negative_net_pnl | 16240 | 246 | -109.605392 | 78.720000 | 19.680000 | 19.680000 | -10.960539 | 0.223828 | 10.985896 |
| XLMZEUR | trend | ok | reject | negative_net_pnl | 16240 | 258 | -125.347928 | 82.560000 | 20.640000 | 20.640000 | -12.534793 | 0.253206 | 12.534793 |
| XLMZEUR | mean_reversion | ok | reject | negative_net_pnl | 16240 | 420 | -187.692667 | 134.400000 | 33.600000 | 33.600000 | -18.769267 | 0.144786 | 18.812830 |
| TRXEUR | trend | ok | keep_testing | insufficient_closed_trades | 6841 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  | 0.000000 |

## Safety

This matrix is research-only. It does not authorize live trading and does not update the strategy registry automatically.
