# AUTOBOT Block 5.1 - Persisted Order Lifecycle Graph - 2026-07-20

## Verdict

**GO - research/shadow safety hardening only.** No paper-capital, live,
promotion, sizing, leverage, derivative or order-routing activation occurred.

## Scope

The persistent order store now owns one canonical lifecycle graph. This closes
the previous gap where a legacy runtime caller could record any status jump,
including a terminal state without the evidence of submission or acknowledgement.

## Delivered behavior

- Canonical states are `NEW`, `SENT`, `ACK`, `PARTIAL`, `FILLED`, `CANCELED`,
  `REJECTED`, `EXPIRED` and `UNKNOWN`.
- Invalid jumps are rejected at the persistence boundary, so they cannot be
  accepted by a direct caller that bypasses the state-machine facade.
- `CANCELLED` is normalized to the canonical persisted `CANCELED` spelling.
- Exact retries of a terminal transition are idempotent and do not append a
  second state-transition record.
- Crash recovery replays the minimum safe path before a discovered fill, for
  example `NEW -> SENT -> ACK -> FILLED`.
- The legacy async protective SELL path records `ACK` before `PARTIAL` or
  `FILLED`; an acknowledgement persistence failure remains `UNKNOWN` and is
  sent to reconciliation rather than being treated as a fill.
- Historical `CANCELLED` rows are treated as terminal during non-terminal
  order recovery without being rewritten.

## Validation

Source revision tested: `bda348d4648abbcd753310c7a45f747271f6da5d`.

- Focused persistence, production-safety, signal-handler and automatic-exit
  suite: `63 passed`.
- Full repository suite: `1773 passed, 6 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.
- Diff scan found no credential material.

## VPS evidence

At the deployed revision, the VPS checkout and AUTOBOT image label matched the
tested commit. The container was `running` and `healthy`; `/health` reported a
running orchestrator, connected WebSocket and 14 instances.

- All four isolated research timers were active after deployment.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.
- Filtered recent logs contained no traceback, critical error, live order or
  live-trading activation.

Generated runtime entries on the VPS worktree were preserved and were neither
reset, cleaned nor committed.

## Residual risks / next gate

- The synchronous legacy `instance.py` path is not part of this async state
  graph migration and remains subject to a separate audit before any paper
  review.
- The graph prevents unsafe local transitions; complete reconciliation of a
  partial or uncertain external fill remains a separate Block 5 task.
- No strategy has qualified for paper-capital or live review.
