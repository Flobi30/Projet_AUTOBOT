# AUTOBOT Block 6 — Deployment Evidence Final Recheck — 2026-07-29

## Decision

**GO — local-only deployment-evidence hardening.** Deployment remains deferred
until the Hetzner VPS is accessible again.

## Finding

The deployment verifier initially confirmed health and a connected WebSocket,
then performed Docker environment and code-level authorization checks before
writing its evidence. The earlier response could have become stale, or the
container could have been replaced, before the final JSON record was emitted.

## Change

- Added a reusable strict health-payload parser.
- Immediately before output, the verifier now checks that the same container
  ID is still running, healthy and using the expected image.
- It then reads `/health` again and requires a fresh `healthy` status plus a
  connected WebSocket before producing any `RuntimeDeploymentEvidence` JSON.
- A hermetic integration test proves that a second, unhealthy response blocks
  evidence even when the initial health response was valid.

## Safety

The verifier remains read-only: it does not build, restart, stop or deploy a
container; alter Git or flags; access secrets; change data; or invoke an order,
paper or live path.

## Required validation

Completed locally:

- `bash -n deploy/verify-autobot-runtime-evidence.sh`;
- deployment-evidence, resilience and monitor-targeted suite: **33 passed**;
- an adversarial second-health-response test which rejects a late WebSocket
  disconnect.

Run the full suite, `git diff --check` and a changed-file secret scan before
commit. Once the VPS returns, run this verifier only after the controlled
deployment workflow and retain its non-secret JSON alongside the corresponding
report.
