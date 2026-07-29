# AUTOBOT Block 2 — research evidence and holdout governance — 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`.

This increment remains research-only. It strengthens the experiment register's
ability to reject untraceable positive research results. It does not activate
shadow routing, paper capital, promotion, live trading, sizing, leverage, or
any order path.

## Scope delivered

- A `PASSED` result at `NET_SMOKE`, `WALK_FORWARD`, or
  `STRESS_MONTE_CARLO` now requires the minimum stage-specific metrics plus a
  content-addressed report artifact. Empty success transitions can no longer
  advance a material experiment.
- Runner evidence binds its immutable report to every passed material stage,
  making each transition independently auditable.
- The material alpha-runner CLI now requires a feature-snapshot manifest, a
  code commit, and an image reference before it can read data or create a
  material experiment. It can no longer run an unregistered material trial.
- A final immutable holdout can now be exclusively claimed by one material
  experiment. A retry by that experiment is idempotent; any other experiment
  is blocked before it can consume the same holdout.
- Final holdout claims appear in exported experiment manifests. Historical
  final-review rows that predate an exclusive claim remain historical only and
  cannot satisfy the `SHADOW_REVIEW` promotion boundary.

## Evidence and tests

- targeted experiment/CLI/shadow-governance suite: `102 passed`;
- expanded research, CLI, paper, strategy-governance and router safety suite:
  completed without failure;
- full repository suite: `1974 passed, 6 skipped, 2 deselected`;
- targeted `py_compile` for the changed registry and CLI: passed;
- `git diff --check`: passed (only local CRLF conversion notices).

The changed modules are restricted to the research CLI, experiment registry,
and hermetic tests. They do not import the execution router, paper engine,
private Kraken client, or runtime orchestrator.

## Safety invariants preserved

- no paper capital, live trading, automatic promotion, sizing, leverage, or
  runtime flag changed;
- no order, fill, private API, scheduler, or runtime service was called;
- grid remains retired from execution;
- a positive research outcome now needs more evidence, never less;
- a holdout can only reduce uncertainty for one frozen material experiment and
  cannot be reused to select another configuration.

## VPS deployment status

Hetzner maintenance prevents controlled VPS access. No VPS checkout, Docker
image, container, service, database, runtime flag, or data was modified by this
increment.

When maintenance ends, deploy only after confirming there is no active research
job. Fast-forward the checkout, run `bash deploy/rebuild-autobot-image.sh`, then
`bash deploy/verify-autobot-runtime-evidence.sh`. Verify the GitHub/VPS/container
commit, `/health`, WebSocket, instance count, observation-only flags, and
absence of orders before marking this block `VERIFIED`.

## Remaining gate

Block 2 is locally complete but `PARTIAL` until the controlled VPS smoke
evidence exists. The registry hardening does not make any alpha valid: every
candidate must still pass net costs, out-of-sample evidence, multiple-testing
controls, and a separately reviewed shadow boundary.
