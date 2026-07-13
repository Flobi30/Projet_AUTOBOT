# AUTOBOT SQLite Restore Drill

This is a research-only recovery check. It does not start AUTOBOT, write to the
runtime state database, create an order, activate paper capital, or enable live
trading.

## Purpose

Verify that an existing SQLite backup can be restored into a disposable local
directory and still contains the same schema and table row counts.

## Command

```text
python -m autobot.v2.cli sqlite-restore-drill --backup-path <immutable-backup.sqlite3>
```

The command opens the input backup read-only, restores it into a temporary
directory, checks SQLite integrity, schema and row counts, verifies the input
hash did not change, then removes the temporary restore.

## Rules

- Use a backup artifact, not a runtime database path.
- Treat any failure as `NO_RESTORE_EVIDENCE`; do not alter runtime state to
  force a passing result.
- Backup scheduling, encryption, retention and off-VPS storage require a
  separate approved design. This drill does not claim those controls exist.
