# AUTOBOT Block 6 — SQLite Restore Drill

Date: 2026-07-13  
Code commit: `606c6babf870c924d916a6f226dd4f14a3823553`

## Decision

GO — AUTOBOT can now verify an existing SQLite backup through a hermetic,
research-only restore drill. This is recovery evidence only; it does not create
a backup schedule, enable paper capital, or authorize live trading.

## Change

- Added `verify_sqlite_restore_drill()` and `SQLiteRestoreDrillManifest`.
- The drill opens the backup read-only, restores it in a disposable temporary
  directory, checks integrity, schema and table row counts, verifies the input
  hash is unchanged, then removes the temporary restore.
- Added `sqlite-restore-drill --backup-path <backup.sqlite3>` to the CLI.
- Added a current research recovery guide and marked legacy micro-live
  instructions as archived and non-authorizing.

## Validation

- Targeted resilience and CLI suite: `40 passed`.
- Full isolated VPS suite: `1571 passed, 4 existing pytest warnings` in
  69.99 seconds.
- The warnings are unrelated asyncio marks on synchronous order-router tests.
- Corrupt and missing backups are rejected; the drill proves it does not modify
  its input backup.

## Deployment Evidence

- GitHub and VPS source were aligned on `606c6babf870c924d916a6f226dd4f14a3823553`.
- The runtime image was rebuilt and `autobot-v2` recreated successfully.
- `/health` stayed healthy with the orchestrator running, WebSocket connected
  and 14 instances.

## Safety Confirmation

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No runtime database was restored or overwritten during this deployment.
- No production backup schedule, encryption, retention or off-VPS storage is
  claimed by this change; those require a separate approved design.
