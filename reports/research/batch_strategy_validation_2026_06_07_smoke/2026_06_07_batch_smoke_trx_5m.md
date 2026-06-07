# Batch Strategy Validation - 2026_06_07_batch_smoke_trx_5m

Generated at: `2026-06-07T15:58:19.379992+00:00`
Data source: `csv`
Data path: `data\research\historical_long_foundation_smoke_2026_06_07\2026_06_07_kraken_smoke_TRXEUR_5m.csv`
Strategies: `grid, trend, mean_reversion`
Symbols: `TRXEUR`
Cost config: `{"fallback_spread_bps": 8.0, "latency_buffer_bps": 1.0, "maker_fee_bps": 10.0, "max_liquidity_participation": 0.05, "max_spread_bps": 80.0, "min_notional_eur": 5.0, "slippage_bps": 4.0, "taker_fee_bps": 16.0}`

## Window Summary

| Window | Cells | Success | Errors | Trades | Net PnL | Profitable Cells | Best | Worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| full | 3 | 3 | 0 | 17 | -7.232615 | 0 | TRXEUR/trend 0 | TRXEUR/mean_reversion -7.145614554581607 |
| early | 3 | 3 | 0 | 10 | -6.120660 | 0 | TRXEUR/trend 0 | TRXEUR/mean_reversion -4.516099673182498 |
| middle | 3 | 3 | 0 | 7 | -1.848788 | 1 | TRXEUR/grid 0.038784579138058384 | TRXEUR/mean_reversion -1.8875723842967336 |
| late | 3 | 3 | 0 | 2 | -0.741942 | 0 | TRXEUR/trend 0 | TRXEUR/mean_reversion -0.7419424971023768 |
| weekend | 3 | 3 | 0 | 9 | -2.555552 | 1 | TRXEUR/grid 0.07396289524959404 | TRXEUR/mean_reversion -2.6295148813991105 |

## Status By Strategy

- `grid`: `research_only`
- `mean_reversion`: `research_only`
- `trend`: `research_only`

## Strategy Decisions

| Strategy | Status | Blockers | Supporting Windows | Failing Windows | Best Symbols | Rejected Symbols | Overfit Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| grid | research_only | non_positive_total_net_pnl, insufficient_total_closed_trades, insufficient_window_stability, dominated_by_single_symbol, no_cell_passes_candidate_thresholds, baseline_no_trade_unavailable, baseline_buy_and_hold_unavailable, baseline_random_signal_unavailable, mfe_to_cost_unavailable, exit_capture_unavailable | - | 2026_06_07_batch_smoke_trx_5m_full, 2026_06_07_batch_smoke_trx_5m_early, 2026_06_07_batch_smoke_trx_5m_middle, 2026_06_07_batch_smoke_trx_5m_late, 2026_06_07_batch_smoke_trx_5m_weekend | TRXEUR:0.112747 | TRXEUR:-1.578814 | high |
| mean_reversion | research_only | non_positive_total_net_pnl, no_positive_net_pnl_cells, profit_factor_below_threshold, insufficient_window_stability, no_cell_passes_candidate_thresholds, baseline_no_trade_unavailable, baseline_buy_and_hold_unavailable, baseline_random_signal_unavailable, mfe_to_cost_unavailable, exit_capture_unavailable | - | 2026_06_07_batch_smoke_trx_5m_full, 2026_06_07_batch_smoke_trx_5m_early, 2026_06_07_batch_smoke_trx_5m_middle, 2026_06_07_batch_smoke_trx_5m_late, 2026_06_07_batch_smoke_trx_5m_weekend | - | TRXEUR:-16.920744 | high |
| trend | research_only | non_positive_total_net_pnl, insufficient_total_closed_trades, no_positive_net_pnl_cells, profit_factor_below_threshold, insufficient_window_stability, no_cell_passes_candidate_thresholds, baseline_no_trade_unavailable, baseline_buy_and_hold_unavailable, baseline_random_signal_unavailable, mfe_to_cost_unavailable, exit_capture_unavailable | - | 2026_06_07_batch_smoke_trx_5m_full, 2026_06_07_batch_smoke_trx_5m_early, 2026_06_07_batch_smoke_trx_5m_middle, 2026_06_07_batch_smoke_trx_5m_late, 2026_06_07_batch_smoke_trx_5m_weekend | - | TRXEUR:0.000000 | high |

## Conclusion

No validation window was net positive after costs; keep strategies research-only.

## Safety

- Batch strategy validation is research-only.
- No runtime paper/live service is started.
- No paper or live order is created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
