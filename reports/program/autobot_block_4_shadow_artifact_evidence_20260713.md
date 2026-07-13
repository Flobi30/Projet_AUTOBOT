# AUTOBOT Block 4 — Shadow Artifact Evidence Binding

## Decision

**GO (research/shadow governance only).** This change adds no trading path and
does not authorize paper capital, live trading, or automatic promotion.

## Scope

`StrategyArtifact` is now bound to immutable experiment evidence whenever its
status is shadow-capable (`SHADOW_ELIGIBLE`, `SHADOW`, `THROTTLED`, or
`QUARANTINED`). The binding contains:

- the experiment identifier;
- its material fingerprint;
- an explicit human approval reference.

The append-only artifact registry independently reads the experiment registry
before persisting a shadow-capable artifact. It requires a terminal, passed
`SHADOW_REVIEW` result and rejects a missing registry, a changed fingerprint,
or incomplete validation evidence.

## Safety properties

- Grid aliases remain retired.
- The new factory cannot set paper, live, or automatic-promotion permissions.
- The registry remains append-only.
- Safety automation can still only reduce risk; it cannot begin shadow or
  relax a throttle.
- This research module imports no runtime order, router, or paper-execution
  module.

## Evidence before deployment

- Focused governance, experiment-registry, and manifest tests: `23 passed`.
- Python compilation of the changed governance module: passed.
- `git diff --check`: passed.

## Residual risk

The runtime remains fail-closed and does not yet consume this artifact registry
as a production shadow router. That integration stays intentionally blocked
until point-in-time data has a valid current-run feature snapshot and an alpha
passes the research gates.

## Deployment verification

This section is completed only after the source commit is pushed, the VPS is
fast-forwarded, its isolated research tests pass, and the unchanged runtime
health and safety flags are verified.
