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

To create one local integrity-checked backup (without claiming encryption):

```text
python -m autobot.v2.cli sqlite-backup \
  --source data/autobot_state.db \
  --backup-path backups/sqlite/<run-id>.sqlite3 \
  --manifest-path backups/sqlite/<run-id>.json
```

The command opens the input backup read-only, restores it into a temporary
directory, checks SQLite integrity, schema and row counts, verifies the input
hash did not change, then removes the temporary restore.

## Rules

- Use a backup artifact, not a runtime database path.
- Treat any failure as `NO_RESTORE_EVIDENCE`; do not alter runtime state to
  force a passing result.
- The repository contains a disabled-by-default systemd backup unit. It may be
  enabled only after an operator has approved retention and encrypted off-VPS
  storage. The local snapshot itself does not claim encryption.
