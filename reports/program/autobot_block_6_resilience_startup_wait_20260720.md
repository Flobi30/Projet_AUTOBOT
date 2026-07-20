# AUTOBOT Block 6 - Runtime resilience startup wait - 2026-07-20

## Verdict

**GO - operational reliability hardening only.** The change prevents a
freshly restarted runtime from being reported as a database or data-integrity
incident merely because its health endpoint has not finished starting.

No paper-capital, live execution, promotion, sizing, leverage, derivative, or
order-path activation is part of this change.

## Finding

The isolated runtime-resilience audit can be scheduled immediately after an
image rebuild. During that short window the AUTOBOT container may still be
starting its health endpoint and WebSocket. The isolated audit then correctly
fails closed, but could record a misleading `SQLITE_CORRUPT` / `DATA_STALE`
incident before the runtime is ready.

Later controlled checks on the same deployed data reported SQLite integrity
`ok`, a connected WebSocket, and fresh market records. This identifies a
startup-readiness race, not evidence of database corruption.

## Delivered behaviour

- `run-autobot-runtime-resilience-audit.sh` waits for a healthy WebSocket state
  for at most 45 seconds before running its read-only container audit.
- The wait is bounded and configurable through
  `AUTOBOT_RUNTIME_RESILIENCE_HEALTH_WAIT_SECONDS`; an invalid value is rejected
  before the audit runs.
- If the endpoint remains unavailable or disconnected after the deadline, the
  audit still runs and retains its fail-closed incident behaviour.
- The systemd unit pins the same 45-second default. The isolated audit remains
  network-disabled, read-only, capability-dropped, and non-authorizing.

## Validation

Code revision: `d588bcfb6ee3736b31f32c7103a0b29476ce6117`.

- Shell syntax: `bash -n deploy/systemd/run-autobot-runtime-resilience-audit.sh`
  passed.
- Targeted deployment, resilience-audit, readiness, and CLI suite: `57 passed`.
- Full repository suite: `1790 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- Static deployment tests prove the bounded health wait and the explicit
  systemd configuration remain present.

## Controlled VPS validation

The deployment procedure must stop both the research timers and their active
services before rebuilding, preserve generated runtime data, install the
versioned resilience-audit systemd service/timer, reload systemd, rebuild only
the AUTOBOT image through the repository deployment helper, and then restore
the timers.

After runtime health is green, the isolated audit must complete successfully
and report `RESILIENCE_HEALTHY`. The smoke also verifies that the checkout and
container image label match and that the runtime safety flags remain unchanged.

## Safety invariants

- `LIVE_TRADING_CONFIRMATION=false` remains unchanged.
- `STRATEGY_ROUTER_LIVE_ENABLED=false` remains unchanged.
- `COLONY_AUTO_LIVE_PROMOTION=false` remains unchanged.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false` remains unchanged.
- The pre-existing `PAPER_TRADING=true` setting is not authorization for
  paper-capital and is not changed by this work.
- No secrets, private keys, private API endpoints, or order endpoints are used
  by the resilience audit.

## Residual risks / next gate

- The startup wait removes only the false-positive readiness race. Real stale
  data, corruption, a disconnected WebSocket, or an unavailable health endpoint
  must continue to be incidents.
- No strategy is eligible for paper-capital or live review.
- The next work remains an evidence-driven audit of the 24-layer matrix; no
  risk-increasing transition is implied by this operational repair.
