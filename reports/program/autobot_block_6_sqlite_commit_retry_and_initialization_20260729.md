# AUTOBOT Block 6 — SQLite commit retry and initialization — 2026-07-29

## Decision

**GO — local runtime-persistence hardening.** VPS deployment remains deferred
while Hetzner is unavailable.

## Finding

The shared SQLite retry wrapper retried a temporary `database is locked` or
`database is busy` error without first rolling back the repository connection.
When the error occurs during `commit()`, the next attempt could inherit a
partially-open transaction. The schema initializer also owned an initialization
lock but did not use it to serialize concurrent callers on the same
`StatePersistence` instance.

## Change

- A retryable write failure now rolls back its repository connection while the
  shared write lock is still held; if rollback fails, AUTOBOT refuses to retry.
- Backoff remains outside the write lock, so no lock is held while waiting.
- `StatePersistence.initialize()` now double-checks and serializes schema
  setup through its existing `_init_lock`.

The change does not alter strategy logic, execution behavior, capital,
position sizing, risk limits, paper/live flags, or the order path.

## Validation

- `python -m pytest tests/test_persistence_db_reliability.py -q` — **26
  passed**.
- `python -m compileall -q src/autobot/v2/persistence.py` — passed.
- New adversarial test: a busy error from `commit()` performs exactly one
  rollback before an idempotent retry.
- New adversarial test: failed rollback refuses the retry rather than carrying
  an uncertain transaction forward.
- New concurrency test: eight simultaneous initialization callers run the
  schema setup exactly once for one persistence instance.

## Remaining scope

This tranche hardens the shared retry path and initialization. Other legacy
writes that currently bypass the shared helper remain a separate, explicitly
scoped follow-up; no broad persistence refactor was mixed into this safety fix.

## Safety

- No VPS, Docker, systemd, flags, database contents, data collection,
  credentials, private API, paper capital, promotion, live trading, sizing,
  leverage, or order path was invoked.
