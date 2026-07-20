# AUTOBOT Block 5 — Automatic Exit OMS Boundary

## Decision

`GO — automatic exits are now bounded by the canonical OMS lifecycle.`

The automatic take-profit, stop-loss and trailing-stop path previously called
the executor directly. It now persists a canonical SELL order before any
executor invocation and records its lifecycle transitions.

## Safety Behaviour

- Missing strategy, decision or signal provenance blocks the exit before the
  executor is called.
- Missing persistence or a rejected `SENT` transition blocks the exit before
  the executor is called.
- An execution rejection is recorded as `REJECTED`.
- A zero fill is recorded as `REJECTED` and does not close the position.
- A partial fill is recorded as `PARTIAL`; AUTOBOT does not incorrectly close
  the full position and the state remains available for reconciliation.
- A full fill follows `SENT → ACK → FILLED` before the position and canonical
  ledger close record are updated.

## Scope Boundary

This is an OMS traceability hardening change. It does not enable paper capital,
live execution, promotion, changes to sizing or leverage, or a new order route.
The existing safety flags remain the authority for all executable paths.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_position_exit_and_allocation.py \
  tests/test_orchestrator_execution_bypass_guards.py \
  tests/test_persistence_db_reliability.py -q
25 passed

python -m compileall -q src
git diff --check
```

The tests prove full-fill traceability, missing-provenance blocking, failed
OMS-send blocking and partial-fill containment.

## Remaining Work

Partial fills intentionally require a later reconciliation/position-reduction
workflow. AUTOBOT will not infer a full close from a partial execution.
