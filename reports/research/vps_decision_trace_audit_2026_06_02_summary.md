# VPS Decision Trace Audit - 2026-06-02

## Objective

Audit whether AUTOBOT can explain runtime paper activity through one canonical chain:

`Signal -> Decision -> Order -> Fill -> Trade -> PnL -> Outcome`

This audit is read-only and research-only. It does not change paper execution, live execution, risk thresholds, sizing, strategy promotion, Kraken access, or dashboard behavior.

## Input

- State database: `data/vps_autobot_state_2026-06-01.db`
- Generated detailed reports:
  - `reports/research/vps_2026_06_02_decision_trace_audit/vps_2026_06_02_decision_trace_audit.md`
  - `reports/research/vps_2026_06_02_decision_trace_audit/vps_2026_06_02_decision_trace_audit.json`
- Tables detected:
  - `decision_ledger`: 3,212 rows
  - `orders`: 5,811 rows
  - `trade_ledger`: 1,142 rows
  - `signal_outcomes`: 1,995 rows

## Result

| Metric | Value |
| --- | ---: |
| Total traces reconstructed | 8,948 |
| Canonical complete traces | 455 |
| Canonical complete ratio | 5.08% |
| Signal without decision | 857 |
| Rejected traces | 2,490 |
| Rejected traces with outcome | 1,241 |
| Execution traces | 5,699 |
| Execution complete traces | 0 |
| Orphan orders | 0 |
| Orphan trades | 555 |
| Linked net PnL EUR | -21.397803 |

## Link Diagnostics

Additional read-only SQL checks show why execution completeness is zero:

| Check | Count |
| --- | ---: |
| Decision events with `decision_id` | 431 |
| Signal events with `signal_id` | 749 |
| Signals with matching decision by `signal_id` | 749 |
| Orders with `decision_id` | 5,686 |
| Orders matching a `decision_ledger` decision event | 0 |
| Orders matching a `decision_ledger` signal event | 0 |
| Trade ledger rows with `decision_id` | 587 |
| Closing trade ledger rows | 555 |
| Closing trade ledger rows with `decision_id` | 0 |
| Trade ledger rows matching a decision event | 0 |
| Trade ledger rows matching an order by `exchange_order_id` | 711 |
| Signal outcomes matching a decision event | 708 |

## Interpretation

The rejected-signal learning path is partially traceable: 1,241 rejected traces already have a later outcome. That is useful.

The execution/PnL path is not yet canonical. Orders and trades exist, and many trades can be linked to orders by `exchange_order_id`, but they do not link back to the `decision_ledger` decision rows. Closing PnL rows also do not carry `decision_id`, so the system cannot yet answer the most important forensic question reliably:

> Which exact signal and decision caused this realized PnL?

This does not prove paper trading is broken. It proves the audit trail is incomplete.

## Recommendation

Next technical step should be a canonical execution trace bridge:

1. Ensure every accepted execution has a `decision_ledger` decision row before order creation.
2. Ensure `orders.decision_id` and `orders.signal_id` reuse that exact canonical decision/signal pair.
3. Ensure opening and closing `trade_ledger` rows carry enough linkage to reconstruct source decision, signal, order, and position lineage.
4. Keep closing PnL linked to the position and to the strategy/engine that opened it.
5. Add tests that a completed paper trade produces one complete trace.

Do not use this audit result to promote any strategy. It is a measurement-quality blocker, not a trading-performance signal.
