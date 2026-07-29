# AUTOBOT Block 5 — Shadow OMS Risk Fill Cap (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the hermetic shadow OMS now enforces a reduced notional
approved by the independent risk decision across partial fills and restart
reconstruction.

## Finding

`RiskDecision.reduced_notional` was stored as immutable risk evidence, but
fill admission only compared cumulative fills with the original intent target.
A shadow order approved for a smaller amount could therefore record fills above
the risk-reduced amount before reaching its original target.

## Change

- The append-only risk decision is loaded with the associated fill admission
  evidence.
- When `reduced_notional` is strictly smaller than the immutable intent target,
  every prospective cumulative fill is rejected above that cap before any fill
  or order event is written.
- Exact completion at the reduced amount transitions the order to `FILLED`.
- The cap is reconstructed from the persisted risk decision after restart.
- Unreduced intents retain the existing tolerance for small price-driven
  overshoots of their original target; this is not a risk increase.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_oms_ledger.py \
  tests/research/test_runtime_oms_ledger_audit.py \
  tests/research/test_runtime_oms_ledger_migration_plan.py \
  tests/research/test_shadow_observation_ledger.py \
  tests/research/test_orphan_position_reconciliation.py \
  tests/test_reconciliation_async_safety.py \
  tests/test_contracts.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted Block 5 regression: `52 passed`;
- diff check: PASS.

The new tests prove that an over-cap fill leaves no ledger row and leaves the
order acknowledged, that an exact cap fill closes the order, and that a
restart retains the reduced cap across partial fills.

## Safety and deployment

- only `src/autobot/v2/research/oms_ledger.py` changed; it is a hermetic,
  shadow-only model with no router, paper engine, exchange client or secret
  import;
- no VPS/SSH action while Hetzner is unavailable;
- no paper capital, live execution, promotion, sizing or leverage change;
- Grid remains retired from execution.

## Residual risk

This confirms admission and reconstruction inside the research OMS model. A
future human-approved paper review must still validate an equivalent invariant
at every actual execution boundary; this change does not activate or connect
the dormant paper engine.
