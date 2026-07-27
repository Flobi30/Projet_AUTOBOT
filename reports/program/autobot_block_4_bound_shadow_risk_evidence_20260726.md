# AUTOBOT — Bloc 4 bound shadow risk evidence — 2026-07-26

## Decision

`GO_RESEARCH_ONLY`.

The isolated contract-shadow simulator no longer accepts a free-standing
`RiskDecision`. It can receive a decision only through immutable,
non-authorizing evidence produced by the side-effect-free pre-trade mandate
gate.

## Boundary

```text
AlphaSignal → TargetPortfolio → capacity review
→ BoundShadowRiskEvidence → OrderIntent → isolated simulator
```

`BoundShadowRiskEvidence` binds a single review to its strategy artifact,
artifact mandate fingerprint, signal, explicit market, target portfolio,
capacity review, target notional and point-in-time evaluation. The factory
requires the `PreTradeAutonomyGate` result to be `ALLOW`; otherwise it emits
no evidence. The pipeline then repeats the binding checks before it can create
an `OrderIntent`.

## Safety invariants

- No evidence means `RISK_EVIDENCE_BLOCKED`; no intent or simulation follows.
- An evidence mismatch for the artifact, mandate, market, decision ID,
  expected edge, target/capacity fingerprint or notional is blocked.
- A blocked, killed or human-review pre-trade outcome cannot become shadow
  evidence.
- The module is research-only, has no runtime router/paper imports and cannot
  authorize paper capital or live trading.
- This change does not start a shadow runtime, send an order, change sizing or
  modify a live/paper flag.

## Validation

- Focused contract/risk/simulator/ledger suite: `62 passed`.
- Research suite: `667 passed, 1 skipped`.
- Full local suite: `1908 passed, 6 skipped, 2 deselected`.
- Python compilation, JSON validation and `git diff --check`: passed.
- VPS smoke: passed after the implementation commit
  `38b36d9d5082400c5be1d1d32596201805899d22` was deployed. Source and image
  matched; `autobot-v2` was healthy with a read-only root filesystem and zero
  restarts. `/health` reported an active orchestrator, connected WebSocket and
  one intentionally bounded observation-only instance.
- All paper execution flags, all live flags and automatic promotion were
  `false`; no private Kraken credential was present in the container and the
  five-minute critical/order-log scan returned zero matches.

## Remaining boundary

The research simulator now preserves snapshot and cost provenance in its
outcome, but the generic `FillEvent` does not yet transport that evidence into
a canonical TCA/reconciliation ledger. That is a separate bounded OMS/TCA
task; it must not be bridged into the dormant paper runtime without an
independent audit.
