# Research/Paper Parity - 2026-06-06

Generated evidence: `reports/research/research_paper_parity_2026-06-06/research_paper_parity_2026-06-06.md`

## Summary

Snapshot: `data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`

Research replayed: TRXEUR/XLMZEUR across grid, trend and mean_reversion.

Official paper ledger loaded: all comparable trade-ledger evidence from the state DB.

## Result

| Metric | Value |
| --- | ---: |
| Buckets | 19 |
| Divergent buckets | 18 |
| Paper trades | 455 |
| Research trades | 973 |
| Paper net PnL | -21.397803 EUR |
| Research net PnL | -456.926628 EUR |

Alignment counts:

- `paper_has_trades_research_missing`: 13
- `paper_missing_research_has_trades`: 4
- `paper_positive_research_negative`: 1
- `no_evidence`: 1

Top diagnostics:

- `decision_trace_missing_for_bucket`: 18
- `research_adapter_missing_official_paper_trades`: 13
- `official_paper_missing_research_trades`: 4
- `runtime_or_sample_difference`: 1

## Interpretation

Research is not yet measuring exactly what official paper is doing.

Key examples:

- Paper official has many dynamic-grid trades that research replay misses.
- Research generates many negative XLMZEUR trades that paper official did not take.
- TRXEUR paper is slightly positive while research replay is negative.
- The ledger has many `realized_pnl_missing` warnings and several slippage anomalies.

## Conclusion

Research/paper parity is not acceptable yet. Do not use research result alone to promote runtime strategies. The next work should reconcile decision traces, symbol mapping and official paper entry/exit reasons before any promotion.
