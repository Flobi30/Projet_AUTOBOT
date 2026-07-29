# AUTOBOT Block 6 — Persistence Shutdown Isolation (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — asynchronous SQLite shutdown is now bounded and isolates a
failed repository close from its siblings. This improves resilience only; it
does not alter research, shadow, paper, live, order-routing, capital, sizing
or deployment behavior.

## Change

Each persistence repository now:

- serializes shutdown with the existing shared write lock;
- waits a bounded `SQLITE_CLOSE_TIMEOUT_SECONDS` period (default: 10 seconds,
  bounded to 1–120 seconds);
- detaches its connection before closing, so a failed or timed-out connection
  cannot be reused;
- reports a fail-closed `sqlite_repository_close_timed_out` error on timeout.

`StatePersistence.close()` attempts all four repositories (`orders`, `audit`,
`positions`, `instance_state`) before raising a single explicit
`sqlite_persistence_shutdown_incomplete` error if any close failed. This
prevents one failed close from stranding sibling aiosqlite workers.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/test_persistence_lifecycle.py \
  tests/test_persistence_db_reliability.py \
  tests/test_cold_restart_recovery_interlock.py -q
python -m pytest tests/test_persistence_compat.py \
  tests/test_persistence_lineage_retention.py \
  tests/test_persistence_lifecycle.py \
  tests/test_persistence_db_reliability.py \
  tests/test_cold_restart_recovery_interlock.py \
  tests/test_runtime_sanity.py \
  tests/test_orchestrator_execution_bypass_guards.py -q
git diff --check
```

Results:

- compilation: PASS;
- focused lifecycle/reliability/recovery suite: `48 passed`;
- expanded persistence/runtime safety regression: `66 passed`;
- diff check: PASS.

New adversarial coverage proves that:

- a failing repository close does not prevent every other repository close;
- all detached repository connections become unusable after a close failure;
- a stalled repository close times out deterministically and is detached.

## Safety and deployment

- no VPS/SSH access was attempted while Hetzner is unavailable;
- no GitHub/VPS/container alignment claim is made for this local commit;
- the persistence shutdown error is fail-closed and does not authorize a
  restart, new entry, paper capital or live execution;
- Grid remains retired from execution.

## Residual risk

The local tests use hermetic connection probes. A future VPS recovery smoke
must still prove clean shutdown against the running container and actual
aiosqlite workers before layer 24 can be marked `VERIFIED`.
