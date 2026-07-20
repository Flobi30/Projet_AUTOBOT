# AUTOBOT Block 5 — Canonical Order Provenance

## Decision

`GO — continue fail-closed OMS hardening.`

New persisted orders must now carry the same minimum identity chain as their
ledger entries: strategy, decision and signal. This narrows the runtime OMS
boundary without enabling any execution mode.

## Implementation

- `OrderRepository.upsert_order` rejects absent/blank `strategy_id`,
  `decision_id` or `signal_id` before opening a write transaction.
- Retired grid aliases are rejected by the common strategy policy before an
  order can be persisted.
- `PersistedOrderStateMachine.new_order` fails early with the specific missing
  provenance reason instead of deferring it to a database write.
- Existing signal-handler call sites already provide those IDs and continue to
  use the persisted state-machine contract.
- Historical orders remain unchanged and quarantined by the prior read-only
  cutover audit.

## Safety Boundary

This change does not activate, route or submit an order. It affects only the
acceptance criteria for a future persistence attempt. Live trading, paper
capital, auto-promotion, leverage and sizing remain outside scope.

## Local Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_persistence_db_reliability.py \
  tests/test_production_safety.py \
  tests/test_signal_handler_async_unit.py -q
46 passed

python -m compileall -q src
git diff --check
```

The tests cover temporary SQLite-lock retry, transition provenance, duplicate
order protection, restart recovery and each missing canonical identity.

## Remaining Work

Automatic position exits still have an older direct executor path. Their
ledger writes now fail closed without trace metadata, but a future Block 5
change must route new exits through the canonical OMS lifecycle or keep them
quarantined as a reduction-only exception.
