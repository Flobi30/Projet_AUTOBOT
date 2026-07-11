# AUTOBOT — Runtime shadow contract preview (2026-07-12)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

## Delivered

The direct-entry guard now emits a compact, non-executable shadow preview for
each blocked BUY signal. It can create the following contracts only when the
signal explicitly supplies its provenance:

```text
AlphaSignal -> TargetPortfolio -> OrderIntent -> rejected RiskDecision
```

No `ExecutionCommand` can be created by this adapter. It imports no executor,
paper engine, order router, or broker client.

## Fail-closed evidence

- No implicit symbol, quote-currency, feature-version, snapshot, availability
  timestamp, expected edge, or notional is invented.
- Missing provenance produces `SHADOW_PREVIEW_REJECTED` with an auditable
  reason.
- Retired grid aliases are rejected.
- A complete, explicit signal produces `SHADOW_PREVIEW_READY`, but its risk
  decision is still rejected as `shadow_preview_only_no_execution`.
- Existing SELL and stop-loss paths remain outside the entry guard.

## Remaining work

This is a diagnostic bridge, not the final runtime integration. The next gate
is to make strategy producers emit the required provenance and to connect the
previewed contracts to an independent shadow risk decision and append-only
shadow OMS ledger. Paper and live remain forbidden.
