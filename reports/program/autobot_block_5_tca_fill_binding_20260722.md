# AUTOBOT Block 5 — TCA Bound to Recorded Fills

## Decision

**GO — hermetic OMS/TCA hardening.** A transaction-cost record is valid only
when it can be tied to one immutable fill in the append-only shadow ledger.

## Change

- `TransactionCostAnalysis` now requires `fill_id`.
- TCA recording requires that fill to exist for the same client order.
- Side, fill price, fee, spread, slippage, latency and funding attribution
  must exactly match the persisted fill evidence.
- A new append-only one-to-one fill/TCA binding prevents a second or altered
  attribution for the same fill.

This model remains hermetic and shadow-only; it does not call an exchange,
paper engine or runtime order router.

## Validation

```text
74 passed
python -m py_compile src/autobot/v2/research/oms_ledger.py: passed
git diff --check: passed
```

The suite covers OMS transitions, duplicate/restart handling, fill costs,
TCA, reconciliation, migration planning, orphan positions, shadow simulation
and contract boundaries.

## Safety

- No paper capital, live trading, promotion, sizing or leverage change.
- `oms_tca_fill_bindings` is append-only.
- Missing or mismatched fill evidence is rejected instead of being inferred.
