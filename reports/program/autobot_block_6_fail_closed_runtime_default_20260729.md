# AUTOBOT - Bloc 6 - Fail-closed runtime default - 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`

The execution-mode selector now defaults to observation-only whenever the
deployment does not contain a complete, deliberate execution authorization.
An absent observation-mode variable can no longer select the legacy private
Kraken executor by accident.

## Scope

- `observation_only_runtime()` remains locked when
  `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`.
- When that variable is absent or set to false, the runtime remains
  observation-only unless either every paper guard or every real-mutation
  guard is present.
- The change does not authorize any execution. The existing real-mutation
  guard remains the final independent protection for `AddOrder` and
  `CancelOrder`.
- Legacy router and nonce tests now explicitly stub the private-executor
  boundary only inside hermetic mock tests. Production safety tests keep the
  real fail-closed boundary.

## Evidence

- Targeted boundary, router, nonce and idempotence tests:
  `115 passed`.
- Full local non-regression suite:
  `1990 passed, 6 skipped, 2 deselected`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Safety

- No live, paper capital, promotion, sizing, leverage or order path was
  enabled.
- No private credential or secret was added.
- No Docker, VPS, database or runtime flag was changed while Hetzner
  maintenance prevents controlled deployment verification.

## VPS follow-up after maintenance

Deploy only after access is restored and no research job is active, using the
controlled rebuild and evidence verifier. The runtime must remain
observation-only with paper, live and automatic promotion disabled. A fresh
VPS evidence record is required before this local change can be marked
runtime-verified.
