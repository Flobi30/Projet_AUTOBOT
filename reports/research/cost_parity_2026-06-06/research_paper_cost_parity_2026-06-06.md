# Cost Parity Audit - research_paper_cost_parity_2026-06-06

## Research Cost Baseline

- Expected per-side effective cost: `25.000000` bps
- Fee per side: `16.000000` bps
- Legacy shadow slippage bucket per side: `9.000000` bps

## Sources

| Source | Status | Trades | Cost Rows | Notional EUR | Fees EUR | Adverse Slip EUR | Favorable Slip EUR | Total Cost EUR | Avg Fee bps | Avg Adverse Slip bps | Avg Total bps | Delta bps | Max Abs Slip bps | Anomaly Rows | Warnings |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| official_paper_trade_ledger | ok | 599 | 1142 | 11505.089462 | 20.184592 | 8.666095 | 2549.882253 | 28.850687 | 17.544055 | 7.532401 | 25.076456 | 0.076456 | 294822.288606 | 24 | slippage_bps_anomalies |
| trend_shadow | not_configured | 0 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  |  |  |  |  | 0 | trend_shadow_not_configured |
| mean_reversion_shadow | not_configured | 0 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  |  |  |  |  | 0 | mean_reversion_shadow_not_configured |
| setup_shadow | not_configured | 0 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |  |  |  |  |  | 0 | setup_shadow_not_configured |

## Warnings

- slippage_bps_anomalies
- trend_shadow_not_configured
- mean_reversion_shadow_not_configured
- setup_shadow_not_configured

## Safety

- Read-only cost parity audit.
- No paper or live order is created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
