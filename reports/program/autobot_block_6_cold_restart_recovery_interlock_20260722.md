# AUTOBOT Block 6 — Cold-restart recovery interlock

Date: 2026-07-22  
Decision: **GO** for this bounded fail-closed recovery hardening. Research and shadow-only boundaries remain unchanged.

## Scope

This delivery removes unsafe ambiguity during cold-start order recovery and exchange
reconciliation. It does not enable paper capital, live trading, promotion, sizing,
leverage, order routing, or strategy execution.

## Delivered

- recovery lookups now distinguish `FOUND`, `CONFIRMED_ABSENT`, and `UNAVAILABLE`;
- an unavailable exchange response can no longer be interpreted as an absent order;
- ambiguous recovery persists `UNKNOWN`, retains the duplicate-order guard, and trips
  the persisted global kill-switch latch;
- unavailable SQLite recovery evidence halts before an exchange lookup;
- persisted global kill state prevents startup attestation from passing;
- reconciliation treats unavailable order-status or open-order evidence as critical,
  halt-required divergence instead of an empty exchange response;
- the global kill-switch database supports a test-isolation path through
  `GLOBAL_KILL_SWITCH_DB_PATH`, while retaining the production default.

## Evidence

| Check | Result |
| --- | --- |
| Code commit | `3ef4d635c294a28f2a72973896d8e7c6db03efc4` |
| Local compilation | `python -m compileall -q src` passed |
| Focused safety/recovery suite | 91 passed |
| Full local suite | 1834 passed, 6 skipped |
| Diff validation | `git diff --check` passed (line-ending notices only) |

The tests use hermetic fakes or temporary SQLite stores. They do not call an exchange
order endpoint and cannot activate paper capital.

## Safety invariants

No runtime flag was changed. Paper execution, paper routing, automatic promotion,
live confirmation, live routing, and instance splitting remain disabled. Grid remains
retired and out of the official runtime path.

## Residual risk and next work

This delivery covers pending-order recovery and exchange-evidence ambiguity. Position
state recovery still needs its own explicit persistence-availability contract before
it can be considered fully cold-restart fail-closed. Research/runtime canonical feature
provenance also remains partial and is a separate parity task. Neither residual risk
authorizes paper capital, promotion, or live trading.
