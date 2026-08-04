# Block 0 - Hermetic test-image completion

## Decision

`GO_VPS_CONTAINER_VALIDATION_PENDING`

## Scope

The dedicated test image is now a complete source tree for hermetic tests that
audit deployment, operator and safety assets. It remains isolated from runtime
data, secrets, network access and the running AUTOBOT container.

## Changes

- Added the required root configuration, documentation, deployment, tool and
  retired-operator assets to `Dockerfile.test`.
- Kept mutable runtime data, databases, logs, secrets and reports excluded by
  `.dockerignore`.
- Marked queue and dispatcher throughput benchmarks as `performance`, so they
  are excluded by
  the documented hermetic test profile rather than acting as a functional test
  on a resource-capped test container.
- Added a contract test that fails if a future test image omits the audited
  source assets.

## Evidence

- Targeted test-image and deployment safety suite: `73 passed, 3 deselected`.
- Full local hermetic suite: `2121 passed, 6 skipped, 5 deselected`.
- The initial VPS test-image run surfaced only missing-source-image assets and
  unmarked performance benchmarks; these image/profile defects are corrected.
  No AUTOBOT runtime behavior was tested or changed.

## Safety

- The test container is run with `--network none`, no runtime volume and
  constrained CPU/memory.
- No production image, runtime database, paper capital, live flag, promotion,
  sizing, leverage or order path is changed by this block.

## Remaining validation

Build and run the corrected image from the committed VPS revision, then verify
the isolated full suite is green. The production service remains untouched;
only its existing health/observation-only state is checked afterwards.
