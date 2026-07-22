# AUTOBOT Block 6 — Position recovery fail-closed

Date: 2026-07-22  
Decision: **GO** for the bounded cold-restart hardening. Research/shadow-only boundaries remain unchanged.

## Scope

This delivery prevents a transient persistence failure from being interpreted as an
empty position or instance-state ledger at startup. It does not activate paper
capital, live trading, promotion, sizing, leverage, or an order path.

## Delivered

- explicit `PositionRecovery` and `InstanceStateRecovery` evidence contracts;
- explicit distinction between readable-empty and persistence-unavailable state;
- atomic in-memory recovery: positions, allocated capital, fee hints and instance
  state are replaced only after both persistence reads are proven available;
- a failed recovery leaves the instance in `ERROR`, without checkpointing an empty
  replacement state;
- an unavailable recovery blocks the orchestrator before WebSocket, dispatcher,
  scheduler, reconciliation, or background tasks start;
- the global kill-switch receives a durable cold-start recovery latch when available;
- regression coverage for the empty-readable, unavailable, no-partial-mutation and
  orchestrator-preflight cases.

## Evidence

| Check | Result |
| --- | --- |
| Code commit | `9d8a815604fe0a59708ef8257f1eb53a7681ae2f` |
| Local compilation | `python -m compileall -q src` passed |
| Targeted recovery/safety suite | 124 passed |
| Diff validation | `git diff --check` passed (line-ending notices only) |

All new tests are hermetic and use temporary SQLite stores or fakes. They do not call
an exchange order endpoint and cannot activate paper capital.

## Safety invariants

No runtime flag is changed. Paper execution, paper routing, automatic promotion, live
confirmation, live routing, and instance splitting remain disabled. Grid remains
retired and out of the official runtime path.

## Residual risk and next work

The older synchronous `instance.py` recovery path remains legacy and requires its own
audit or retirement proof. Canonical feature provenance has a separate gap: research
snapshots are verified, but the legacy runtime has not yet consumed their vectors.
Neither item authorizes paper capital, promotion, or live trading.
