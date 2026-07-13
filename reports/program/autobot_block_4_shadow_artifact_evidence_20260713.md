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

## Test isolation follow-up

The VPS validation image deliberately mounts the repository read-only. The
daily-collection test originally relied on default relative canonical output
directories, which pointed into that read-only checkout. Its fixture now
directs every temporary raw, canonical, manifest, feature and quarantine path
to its own temporary directory. This preserves the production defaults while
proving that the test suite does not require a writable source tree.

## Residual risk

The runtime remains fail-closed and does not yet consume this artifact registry
as a production shadow router. That integration stays intentionally blocked
until point-in-time data has a valid current-run feature snapshot and an alpha
passes the research gates.

## Deployment verification

Source and runtime were verified on the VPS after the final implementation
commit `17a2f1c17d277eb0656dc58a5cc9a39bbb32dfc9`; the test-isolation follow-up
is recorded in commit `64e3ce169d3859bdfdf01f3a13c52360c7b185c7`.

- GitHub and `/opt/Projet_AUTOBOT` are aligned on `64e3ce1`.
- The isolated research test image ran `435 passed` against a read-only source
  mount, with the test cache disabled.
- The production `autobot-v2` container was rebuilt/recreated from the updated
  source and returned `/health: healthy` with its WebSocket connected and
  fourteen instances running.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`;
  `LIVE_TRADING_CONFIRMATION=false`;
  `STRATEGY_ROUTER_LIVE_ENABLED=false`; and
  `COLONY_AUTO_LIVE_PROMOTION=false`.
- No matching critical error, live-order, Kraken-live-order or live-activation
  log line was found after restart.
- The VPS has approximately 61 GiB free storage; no storage pressure blocks
  the research collectors.
