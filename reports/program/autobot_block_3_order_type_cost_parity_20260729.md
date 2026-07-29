# AUTOBOT Block 3 — Entry Order-Type Cost Parity (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the contract-shadow simulation now rejects a validated cost
profile whose entry order type cannot match the only order type the v1
research hand-off can represent.

## Finding

The hand-off does not carry a limit price and the simulator previously defaulted
the missing order type to `market`. A maker/limit cost profile could therefore
pass fingerprint parity while the simulator applied market/taker execution.
That makes the claimed pessimistic edge economically inconsistent.

## Change

- The hand-off declares its only supported entry type explicitly as `market`.
- Before computing scenario-edge results or constructing a target, it rejects
  a scenario-derived cost profile whose `default_entry_order_type` is not
  `market` with `simulation_entry_order_type_cost_model_mismatch`.
- The non-executable `OrderIntent` metadata now records `order_type=market`,
  so the simulator has no implicit fallback at this boundary.

Limit/maker research requires a later, separately reviewed contract carrying a
limit price, risk-mandate order-type evidence and realistic fill rules. It is
not silently approximated by this market-only v1 path.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_contract_shadow_pipeline.py \
  tests/research/test_execution_simulator.py \
  tests/research/test_execution_cost_model.py \
  tests/research/test_portfolio_construction.py \
  tests/research/test_portfolio_shadow_review.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted Block 3 regression: `63 passed`;
- diff check: PASS.

The new test proves that a maker/limit configuration is rejected before it can
produce a target, `OrderIntent`, fill or shadow outcome. Existing exact
pessimistic market-cost derivation remains accepted.

## Safety and deployment

- research/shadow contract path only;
- no router, executor, paper engine or runtime service import added;
- no VPS/SSH action while Hetzner is unavailable;
- no paper capital, live execution, promotion, sizing or leverage change;
- Grid remains retired from execution.

## Residual risk

This closes the market-vs-maker ambiguity for the current v1 hand-off. It does
not implement a maker/limit execution model; that requires its own explicit
price, fill and risk-mandate contract plus later runtime evidence.
