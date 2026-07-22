# AUTOBOT Block 3 — Shadow Order Metadata Safety

## Decision

**GO — research/shadow simulator hardening.** A limit instruction without a
limit price is not a valid executable intent. The isolated simulator formerly
passed that incomplete metadata to the generic fill model, which could treat
it as an executable limit fill.

## Change

Before creating a `FillRequest`, the research-only simulator now rejects:

- unknown order types (`unsupported_order_type`);
- malformed limit prices (`invalid_limit_price`);
- a limit instruction without `limit_price` (`limit_price_required`).

Every failure is a terminal non-fill with the normal shadow order-event audit
trail. No runtime router, paper executor or exchange client is imported.

## Validation

```text
78 passed
python -m py_compile src/autobot/v2/research/execution_simulator.py: passed
git diff --check: passed
```

The suite covers portfolio/capacity, central and pessimistic cost scenarios,
market provenance, funding/basis research, simulator idempotence and the new
limit-order fail-closed cases.

## Safety

- Shadow/research only.
- No paper capital, live trading, promotion, sizing or leverage change.
- The simulator still cannot create an `ExecutionCommand`.
