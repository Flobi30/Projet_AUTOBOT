# AUTOBOT — Runtime entry safety hardening (2026-07-12)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

The historical direct-entry path in `SignalHandlerAsync` is not yet connected
to the canonical `TargetPortfolio -> RiskDecision -> OrderIntent` contracts.
It is therefore fail-closed for new BUY entries by default.

## Scope

- New direct BUY entries require the explicit, opt-in environment switch
  `AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED=true`.
- SELL exits, stop-loss handling, and isolated replay/shadow observation jobs
  are not changed by this guard.
- No paper capital, live execution, promotion, sizing, leverage, or UI change
  is introduced.

## Evidence required before re-enabling

1. Runtime signal conversion to `AlphaSignal` and `TargetPortfolio`.
2. Mandatory independent `RiskDecision` before `OrderIntent`.
3. Central OMS state machine and ledger/reconciliation integration.
4. Contract, integration, failover, and VPS smoke evidence.

## Residual risk

The runtime portfolio/OMS implementation remains incomplete. This guard
reduces exposure while preserving exits; it does not claim that the paper fill
model or the remaining runtime execution path is production-ready.
