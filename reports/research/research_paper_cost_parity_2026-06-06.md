# Research/Paper Cost Parity - 2026-06-06

Generated evidence: `reports/research/cost_parity_2026-06-06/research_paper_cost_parity_2026-06-06.md`

## Summary

Research validation uses `ExecutionCostConfig` defaults:

| Source | Maker fee | Taker fee | Spread | Slippage | Latency | Config source | Research | Paper official | Live potential |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `ExecutionCostModel` | 10 bps | 16 bps | 8 bps fallback | 4 bps | 1 bps | `src/autobot/v2/research/execution_cost_model.py` | yes | no direct | no |
| `strategy-experiments` | 10 bps | 16 bps | 8 bps | 4 bps | 1 bps | CLI/default cost config | yes | no direct | no |
| `grid-experiments` | conservative research profile | 16 bps intended | 8 bps | 4 bps | 1 bps | research runner | yes | no direct | no |
| `PaperTradingExecutor` / official ledger measured | n/a measured | avg fee 17.544 bps | not recorded as spread | avg adverse slip 7.532 bps | not isolated | `trade_ledger` evidence | no | yes | no |
| `OrderRouter` / cost edge | dynamic runtime edge model | variable | variable | variable | buffer | runtime config/logs | no | possible | yes if live allowed |
| `trade_ledger` official | measured rows | measured rows | missing/zero field | measured slippage_bps | not isolated | SQLite state DB | audit input | yes | no |

## Evidence

- Official paper ledger: 599 trades, 1142 cost rows.
- Total notional: 11505.09 EUR.
- Average fee: 17.544 bps.
- Average adverse slippage: 7.532 bps.
- Average total measured cost: 25.076 bps.
- Research expected cost per side: 25.000 bps.
- Delta: +0.076 bps, so average research costs are close to paper official.
- Warning: 24 slippage anomalies, max absolute slippage bps about 294822 bps.
- Shadow DBs were not configured in this run.

## Profiles Proposed

| Profile | Purpose | Fee | Spread | Slippage | Latency | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `conservative_research` | keep current guardrail | 16 bps taker | 8 bps | 4 bps | 1 bps | keep |
| `paper_official_equivalent` | reproduce current paper average | 17.5 bps measured | unknown | 7.5 bps measured | not isolated | needs better ledger fields |
| `exchange_realistic` | future Kraken-aware | Kraken fee tier + live bid/ask | observed bid/ask | venue model | observed latency | later, not now |

## Conclusion

Do not lower costs. Average costs are not the biggest mismatch. The bigger issue is data/ledger quality: paper has slippage anomalies and research/paper decision divergence.
