# AUTOBOT Block 6 — Global kill-switch store fail-closed hardening

Date: 2026-07-22  
Decision: **GO** for the persistence-safety hardening; research/shadow boundaries remain unchanged.

## Scope

This change makes the persisted global kill-switch fail closed when SQLite storage is
temporarily unavailable. It does not activate paper capital, live trading, strategy
promotion, order routing, sizing, or leverage.

## Delivered

- bounded SQLite connection timeout, busy timeout, and retries for the global
  kill-switch store;
- storage read failures now produce a tripped, recovery-required state instead of an
  implicit allow;
- a missing persisted state row is also fail-closed;
- recovery acknowledgement persists successfully before the in-memory kill switch can
  clear;
- dashboard acknowledgement returns a service error when durable acknowledgement
  fails, rather than re-arming unsafely;
- the global status snapshot exposes storage health for operational diagnosis;
- adversarial tests cover locked/unavailable storage and the durable-acknowledgement
  ordering.

## Evidence

| Check | Result |
| --- | --- |
| Code commit | `ee1636223028be55e53ff46d0f684f1faa89399a` |
| Local compilation | `python -m compileall -q src` passed |
| Local focused safety/resilience suite | 128 passed |
| VPS isolated Docker suite | 128 passed in 3.72s |
| VPS Git / image revision | aligned on `ee1636223028be55e53ff46d0f684f1faa89399a` |
| Container health | running, healthy |
| Runtime health | orchestrator running, WebSocket connected, 14 instances |
| Global kill store | readable; untripped and not recovery-required at validation time |
| Runtime critical/live-order scan | no matches since deployment |

The VPS test suite was run in an isolated, network-disabled, read-only container with
only a temporary writable filesystem. It cannot route orders or modify the runtime
repository.

## Safety invariants rechecked

All of the following remained `false` after deployment:

- `PAPER_EXECUTION_ADAPTER_ENABLED`
- `PAPER_EXECUTION_ROUTER_ENABLED`
- `PAPER_TEST_TRADING_ENABLED`
- `PAPER_DYNAMIC_CAPITAL_REBALANCE_ENABLED`
- `COLONY_PAPER_AUTOPILOT_ENABLED`
- `COLONY_AUTO_SCALE_PAPER_CHILDREN`
- `COLONY_AUTO_LIVE_PROMOTION`
- `LIVE_TRADING_CONFIRMATION`
- `STRATEGY_ROUTER_LIVE_ENABLED`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR`

The existing `PAPER_TRADING=true` legacy safety mode was not changed and does not
grant paper-capital authority.

## Residual risk and next work

If persistent storage becomes unrecoverably unavailable, a local process fails closed,
but cross-process propagation cannot be guaranteed until the store itself is restored.
This is intentionally conservative: new execution remains disabled and any future
paper review must require reconciliation after storage recovery.

Next work remains an audit of the remaining partial layers (cold restart,
reconciliation, and research/runtime feature parity). No alpha currently qualifies for
promotion, paper capital, or live trading.
