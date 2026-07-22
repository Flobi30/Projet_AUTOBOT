# AUTOBOT Block 3 — Funding Carry Attribution

## Decision

**GO — research-only clarification.** The current `funding_basis` adapter is
a spot-EUR directional replay. It does not open, hedge, or account for a
Kraken Futures perpetual position. Historical funding and basis are therefore
point-in-time features, not cash flows belonging to its simulated spot trade.

Charging a perpetual funding payment to this adapter would make the result
economically false. Omitting the distinction would be ambiguous. The adapter
now records an explicit `funding_carry_eur = 0.0` and a structured
`funding_carry_attribution` with the reason
`spot_only_directional_context_no_perpetual_position`.

## Guardrails added

- `FundingBasisTrade` rejects every non-zero funding carry.
- Aggregate metrics expose `total_funding_carry_eur`, which is zero for this
  spot-only adapter.
- Research trade-journal records preserve the attribution metadata.
- Perpetual USD prices remain directional context only; no implicit USD/EUR
  conversion and no derivatives execution path were introduced.

## Validation

Local targeted suite:

```text
77 passed
```

Covered funding/basis smoke, walk-forward, statistical records, execution
costs, shadow contracts, microstructure evidence, portfolio construction and
the central contract suite. `python -m compileall -q src` and
`git diff --check` also passed.

## Safety

- Research/shadow only.
- No paper capital, live trading, promotion, order routing, sizing or leverage
  change.
- Grid remains retired/no-go.
- Any future true derivatives strategy needs a separate position and funding
  cash-flow model; it cannot reuse this zero-carry spot attribution.
