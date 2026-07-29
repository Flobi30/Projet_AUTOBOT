# AUTOBOT Block 3 — Research Sizing Contract

## Decision

`GO_LOCAL_ONLY` — introduce a deterministic, non-executable boundary between
portfolio construction and risk review. No paper-capital, live, sizing-rule or
runtime order-path permission changed.

## Scope

The new `SizingDecision` contract binds exactly one:

```text
AlphaSignal → TargetPortfolio → PortfolioCapacityReview → SizingDecision → RiskDecision
```

It is used only by the fail-closed runtime shadow bridge. The output can record
a bounded shadow proposal; it cannot create an `OrderIntent`, fill, command or
capital allocation.

## Safety invariants

- The target, capacity review, strategy artifact, market and risk-mandate
  fingerprints must match exactly.
- Capacity is the sole source of the proposed notional; it must equal the
  target weight multiplied by the reference capital.
- The mandate must be current and caps the proposed notional through
  `shadow_notional_max_eur`.
- A missing, expired, mismatched, failed-capacity or tampered sizing decision
  is rejected.
- A `CAPACITY_OK` review requires one fresh, research-only estimate and one
  immutable evidence fingerprint for every target market; it cannot be
  hand-constructed from an empty or incomplete proof set.
- Target construction time, capacity-review time and signal availability must
  be identical. This prevents a mandate from being evaluated before it has
  expired and reused later.
- The approved risk evidence stores the canonical sizing fingerprint. A risk
  review cannot be replayed with a different sizing object, even if the amount
  is superficially identical.
- `research_only=true`, `paper_capital_allowed=false` and `live_allowed=false`
  are enforced by the contract.
- The sizing module statically excludes order router, paper engine, Kraken and
  legacy allocator imports.

## Explicit non-goals

- Do not alter legacy runtime pyramiding/volume calculations. Their direct
  execution path remains fail-closed.
- Do not create a paper allocation, an order, a fill or an execution command.
- Do not claim a production sizing model or a promotion gate.

## Local validation

```text
pytest tests/research/test_portfolio_sizing.py
       tests/research/test_runtime_shadow_decision_bridge.py
       tests/research/test_portfolio_construction.py
       tests/research/test_contract_shadow_pipeline.py
       tests/test_contracts.py -q
43 passed

python -m compileall -q src
PASS

python -m pytest -q
PASS (full local regression suite)
```

After adversarial review, the sizing/capacity/risk boundary regression suite
was extended and passed:

```text
71 passed
```

The complete contract, risk and handler boundary suite then passed:

```text
108 passed
```

VPS deployment evidence is recorded only after this increment is committed and
SSH access is restored; this report makes no runtime claim.

## Remaining gate

`PARTIAL`: the contract is implemented and locally tested. It requires the
full regression suite, GitHub push and controlled VPS smoke evidence before a
block-level end-to-end status can change.
