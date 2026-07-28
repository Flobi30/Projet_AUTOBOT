# AUTOBOT Block 6 — SQLite resilience backup bundle — 2026-07-29

## Decision

**GO_LOCAL / REWORK_FOR_VPS_VALIDATION**

Commit implementing this bounded increment: `c5e7194d69d4b2d14f3c3e255e2e3785d43c996c`.

The increment remains research/observation-only.  It does not activate paper
capital, live trading, strategy promotion, sizing, leverage, a broker client or
an order path.

## Delivered boundary

The disabled-by-default systemd backup job now creates a fixed local SQLite
resilience bundle rather than snapshotting only the runtime state database.

| Scope entry | Status when absent | Reason |
| --- | --- | --- |
| `data/autobot_state.db` | fail closed | Runtime state and append-only ledger |
| `data/global_kill_switch.db` | fail closed | Persistent fail-closed kill-switch |
| `data/research/experiment_registry.sqlite3` | explicit optional skip | Research may not have produced a registry yet |
| `data/research/strategy_artifacts.sqlite3` | explicit optional skip | Governance may not have produced an artifact yet |

The scope is versioned, fixed in code and limited to `data/`; it does not scan
arbitrary files, mount secrets or create absent research registries.

Every present database is copied through SQLite's backup API, integrity-checked
and fingerprinted. The manifest records a capture start/end window. This is a
**sequential** set of individual database snapshots, not a falsely claimed
cross-database transaction.

## Operator safeguards

- The systemd unit still sets `AUTOBOT_SQLITE_BACKUP_ENABLED=false`.
- The job still requires `AUTOBOT_SQLITE_BACKUP_EXTERNAL_POLICY_APPROVED=true`
  before it can run.
- The isolated container has no network, a read-only root filesystem, no Linux
  capabilities and only read-only `data/` plus a dedicated local backup mount.
- Backup run identifiers reject traversal and unsafe characters.
- No upload, encryption claim, retention purge or automatic restore was added.
- Restoring a kill-switch database into a runtime location remains a separate
  human-led procedure and must never automatically clear a `tripped` state.

## Commands

Read-only inventory:

```text
python -m autobot.v2.cli sqlite-backup-scope-audit --repo-dir .
```

The bundle command is available for the disabled service after a separate
human policy decision:

```text
python -m autobot.v2.cli sqlite-backup-bundle \
  --repo-dir . \
  --bundle-path backups/sqlite/<run-id>
```

## Verification

| Check | Result |
| --- | --- |
| Scope/bundle/CLI focused tests | `68 passed` |
| B5/B6 resilience and deployment-safety tests | `88 passed` |
| Full test suite | `1943 passed, 6 skipped, 2 deselected` |
| Python compilation | passed |
| JSON matrix validation | passed |
| Shell syntax | passed |
| Disabled backup script | exits without running a backup |
| Unsafe backup run identifier | rejected |
| Diff check and secret-pattern scan | passed; no secret-like material found |

## Remaining gate

The new commit has not been deployed because SSH to `autobot-vps` at the last
check timed out. No VPS service, Docker image, database, flag or runtime state
was changed by this increment.

After SSH recovers, the only authorized next deployment action is the existing
controlled rebuild followed by the read-only deployment-evidence smoke. The
backup unit remains disabled even after that validation until a human approves
retention and encrypted off-VPS storage.
