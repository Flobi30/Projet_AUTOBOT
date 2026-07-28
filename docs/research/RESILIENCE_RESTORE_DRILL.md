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

The disabled-by-default systemd job uses the fixed resilience bundle below,
not a broad scan of `data/`:

```text
required: data/autobot_state.db
required: data/global_kill_switch.db
optional: data/research/experiment_registry.sqlite3
optional: data/research/strategy_artifacts.sqlite3
```

Inspect this scope without writing anything:

```text
python -m autobot.v2.cli sqlite-backup-scope-audit --repo-dir .
```

When an operator has separately approved retention and encrypted off-VPS
storage, the disabled job can create one local **sequential** bundle:

```text
python -m autobot.v2.cli sqlite-backup-bundle \
  --repo-dir . \
  --bundle-path backups/sqlite/<run-id>
```

Each SQLite file is captured with SQLite's backup API and integrity-checked.
The bundle manifest records the capture start/end times: it must never be
treated as a transactionally atomic snapshot across multiple databases. Missing
optional research registries are recorded as skipped and are never created.

To prove a backup/restore cycle without retaining any backup artifact:

```text
python -m autobot.v2.cli sqlite-ephemeral-restore-drill \
  --source data/autobot_state.db
```

When this is run in an isolated container, the temporary filesystem must hold
both the backup and disposable restore; budget at least three times the current
SQLite database size. The command remains read-only against its source.

The command opens the input backup read-only, restores it into a temporary
directory, checks SQLite integrity, foreign-key consistency, schema and row
counts, verifies the input hash did not change, then removes the temporary
restore.

## Rules

- Use a backup artifact, not a runtime database path.
- Treat any failure as `NO_RESTORE_EVIDENCE`; do not alter runtime state to
  force a passing result.
- The repository contains a disabled-by-default systemd backup unit. It may be
  enabled only after an operator has approved retention and encrypted off-VPS
  storage. The local snapshot itself does not claim encryption.
- The backup job never uploads, purges, restores, starts AUTOBOT or enables an
  order path. Restoring a kill-switch database into a runtime location is a
  separate human-led recovery procedure; it must never clear a `tripped` state
  automatically.
