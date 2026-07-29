# AUTOBOT Block 6 — Audit, position and instance SQLite retry

## Scope

Local-only B6 resilience hardening for the shared SQLite persistence layer.
This change does not alter strategy decisions, allocation, sizing, order routing,
paper-capital state, live flags, or VPS configuration.

## Change

- `_with_write_retries()` now rolls back a failed shared write transaction before
  surfacing a non-retryable error as well as before a retryable busy/locked retry.
  A later repository cannot inherit an abandoned transaction.
- `AuditRepository.append_audit_event()` now uses the shared write lock and
  bounded SQLite retry path. Its previous-hash read and insert are enclosed in a
  short `BEGIN IMMEDIATE` transaction, preserving the audit hash chain when
  multiple local processes contend for the database.
- `PositionRepository.save_position()` and `update_position_status()` now use
  the shared retry path.
- `InstanceStateRepository.save_instance_state()` now uses the shared retry
  path.

## Evidence

Commands run locally:

```text
python -m py_compile src/autobot/v2/persistence.py
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_persistence_db_reliability.py \
  tests/test_persistence_compat.py \
  tests/test_position_exit_and_allocation.py \
  src/autobot/v2/tests/test_order_router.py -q
python -m compileall -q src
git diff --check
```

Result: **84 passed**. Compilation and whitespace validation passed.

New regression coverage proves:

- audit append retries a temporary busy error before the hash-chain transaction;
- two persisted audit events chain correctly from the genesis hash;
- position creation, position-status update, and instance-state writes retry a
  temporary SQLite lock without silently dropping the write;
- retry rollback remains visible and bounded.

## Safety

- No Kraken private endpoint, order endpoint, shadow run, paper-capital action,
  promotion, sizing/leverage change, or live flag was used or changed.
- Grid remains outside the official runtime path.
- This is an in-process shared-lock improvement. Cross-process contention still
  relies on SQLite WAL, `busy_timeout`, bounded retries, and the short audit
  transaction; it must be exercised on the Linux VPS after service restoration.

## VPS status

The Hetzner VPS is unavailable because of the reported provider/account
maintenance. No SSH attempt, deployment, rebuild, restart, or remote data
collection was performed.

## Decision

**GO (local only).** The change is ready to commit and push. VPS deployment and
runtime evidence remain deferred until the server is restored.
