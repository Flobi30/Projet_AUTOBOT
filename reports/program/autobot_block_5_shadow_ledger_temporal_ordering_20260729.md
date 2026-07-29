# AUTOBOT Block 5 — Shadow Ledger Temporal Ordering

## Decision

`GO_LOCAL_ONLY` — the hermetic shadow OMS ledger now rejects temporally
impossible evidence before it can alter reconstructed positions, accounting,
reconciliation or TCA. No runtime router, paper engine, live flag, promotion,
sizing/leverage rule or order path changed.

## Scope

The append-only research ledger now enforces:

```text
registered intent
→ approved risk decision at/after intent creation
→ strictly later order lifecycle events
→ strictly later fill
→ derived partial/filled terminal state
```

The existing state-machine transition validation remains in force. The new
time-order validation complements it: an event with a valid type but an older
timestamp is no longer accepted, and a fill cannot be recorded at or before
the latest acknowledged/partial/recovered state.

## Safety invariants

- A risk decision cannot approve an intent before that intent exists.
- A new, non-duplicate order event must strictly follow the latest event.
- A fill must strictly follow the current allowed order state.
- Out-of-order evidence is rejected before database insertion and before any
  position/accounting reconstruction.
- Duplicate event/fill semantics remain idempotent.
- The ledger remains research/shadow-only and imports no runtime router,
  executor or paper engine.

## Local validation

```text
python -m compileall -q src
PASS

PYTHONPATH=src python -m pytest \
  tests/research/test_oms_ledger.py \
  tests/research/test_runtime_oms_ledger_audit.py \
  tests/test_persistence_db_reliability.py \
  tests/test_cold_restart_recovery_interlock.py -q
56 passed

PYTHONPATH=src python -m pytest -q
2053 passed, 6 skipped, 2 deselected
```

The focused tests cover intent/risk ordering, out-of-order lifecycle events,
stale fills, valid later fills, restart reconstruction and reconciliation.

## Deployment state

The Hetzner VPS remains unavailable. No SSH, deployment, Docker action,
runtime mutation, database write, collector or order path was attempted. A
controlled VPS smoke remains deferred until access is restored.

## Remaining gate

Layer 22 remains `PARTIAL`. This closes a chronology gap in the hermetic
research ledger; runtime OMS migration and a future paper-review deployment
remain separate, human-governed work.
