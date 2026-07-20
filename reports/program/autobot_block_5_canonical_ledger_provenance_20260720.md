# AUTOBOT Block 5 — Canonical Ledger Provenance

## Decision

`GO — retain research/shadow-only boundaries and continue Block 5 hardening.`

This change closes the persistence boundary identified by the prior cutover
audit: a new runtime trade-ledger row can no longer look official while lacking
the evidence needed to trace it end to end.

## Scope

- Require `strategy_id`, `decision_id` and `signal_id` for every new
  `StatePersistence.append_trade_ledger` write.
- Require explicit `shadow_paper` or promotion-gated `paper_capital` mode;
  `legacy_unspecified` is rejected for new API writes.
- Require finite fees and slippage evidence before an insert is attempted.
- Make the existing signal-handler ledger path declare `shadow_paper`.
- Preserve trace IDs on automatic position exits when they are present in the
  position metadata. Old positions that lack them may still be risk-reduced,
  but cannot create an untraceable official ledger row.
- Preserve historical SQLite rows unchanged. They remain quarantined by the
  prior read-only cutover audit and are not silently migrated.

## Explicit Non-Goals

- No live, paper-capital, automatic-promotion, sizing or leverage change.
- No new order path, private endpoint, secret access or runtime-database
  migration.
- No claim that legacy ledger history is canonical or eligible for promotion.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_persistence_compat.py \
  tests/test_persistence_db_reliability.py \
  tests/test_pf_phase2.py \
  src/autobot/v2/tests/test_pair_attribution.py \
  src/autobot/v2/tests/test_autonomous_review.py \
  src/autobot/v2/tests/test_consolidated_profitability_review.py \
  tests/test_position_exit_and_allocation.py -q
40 passed

$env:PYTHONPATH='src'; python -m pytest tests/test_signal_handler_async_unit.py \
  -k "execute_sell_records_realized_pnl_from_close_result or sell_signal_persists_canonical_decision_before_order_and_trade" -q
2 passed, 21 deselected

$env:PYTHONPATH='src'; python -m pytest -q
1746 passed, 6 skipped

python -m compileall -q src
git diff --check
```

The focused persistence tests prove that absent decision, signal, fees,
slippage or explicit mode results in zero new ledger rows. A raw historical
row remains readable only as legacy/unattributed evidence and stays excluded
from official strategy metrics.

## Residual Risk

The legacy runtime automatic-exit path is not yet a fully canonical OMS flow.
This change prevents it from contaminating official metrics if an old position
lacks trace metadata, but a later Block 5 task must either route all future
exits through the canonical OMS lifecycle or retain the existing fail-closed
quarantine.

## Deployment Gate

Deploy only after preserving runtime artefacts, stopping research-only timers,
rebuilding through `deploy/rebuild-autobot-image.sh`, and confirming the
container revision, health endpoint, safety flags and no-order log boundary.
