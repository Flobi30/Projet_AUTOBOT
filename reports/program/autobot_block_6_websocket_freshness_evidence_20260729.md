# AUTOBOT Block 6 — WebSocket Freshness Evidence — 2026-07-29

## Decision

**GO — local-only resilience hardening.** VPS validation is intentionally
deferred because Hetzner access remains unavailable.

## Finding

The isolated runtime-resilience monitor previously forwarded a declarative
`connected` WebSocket status without recording when `/health` had supplied that
fact. A delayed monitor or stale caller input could therefore have reported
`RESILIENCE_HEALTHY` after the evidence had become too old.

## Change

- `RuntimeResilienceAudit` now records `websocket_observed_at`,
  `websocket_age_seconds` and `max_websocket_age_seconds`.
- A `connected` status requires a valid, non-future UTC timestamp within the
  configured 60-second window by default.
- Missing, future or stale connected evidence maps to the existing
  fail-closed `WEBSOCKET_DISCONNECTED` incident and blocks new orders in the
  future risk envelope.
- The isolated systemd monitor captures the timestamp immediately after the
  localhost `/health` observation and passes it into the read-only CLI audit.

## Safety

- No runtime service, database, data collector, scheduler, dashboard, order
  router, paper capital flag, live flag, sizing or leverage was changed.
- The monitor retains `--network none`, a read-only data mount, no secrets and
  no order-path imports.
- This is evidence only; it does not execute the recovery steps it models.

## Required validation

Completed locally:

- `bash -n deploy/systemd/run-autobot-runtime-resilience-audit.sh`;
- targeted runtime-audit, deployment and CLI suite: **56 passed**;
- full repository suite: **2055 passed, 6 skipped, 2 deselected**;
- `git diff --check` and a changed-file secret-pattern scan.

After Hetzner is restored, deploy through the controlled workflow and verify
the systemd audit produces a fresh timestamped observation on the same
GitHub/VPS/container commit. No VPS check was attempted while access is
unavailable.
