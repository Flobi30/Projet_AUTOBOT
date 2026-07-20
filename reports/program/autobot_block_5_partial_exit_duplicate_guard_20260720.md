# AUTOBOT Block 5 — Partial Exit Duplicate Guard

## Decision

`GO — partial exits remain contained until reconciliation.`

Before creating an automatic SELL order, AUTOBOT now checks the persisted OMS
for an existing non-terminal SELL on the same symbol. A partial automatic exit
therefore blocks repeat automatic submissions rather than multiplying exits.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_position_exit_and_allocation.py \
  tests/test_persistence_db_reliability.py \
  tests/test_production_safety.py -q
28 passed
```

The partial-fill test verifies that the first attempt becomes `PARTIAL`, the
position remains open, and a second automatic trigger does not call the
executor or create a second order.

## Scope

No paper-capital, live, sizing, leverage, promotion or new order route is
enabled. This is an idempotence guard around an existing safety-reducing path.
