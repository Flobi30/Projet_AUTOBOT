# AUTOBOT Block 6 — Verified SQLite backup readiness (2026-07-16)

## Decision

`GO_FOR_DISABLED_DEPLOYMENT`.

This change adds a reproducible local SQLite snapshot mechanism and a
disabled-by-default systemd schedule. It does not authorize paper capital,
live trading, automatic promotion, order routing or changes to sizing/leverage.

## Controls implemented

- `sqlite-backup` opens its source database read-only, uses SQLite's backup API,
  checks the resulting snapshot integrity and emits a checksum manifest.
- The source and destination must differ; the command refuses to claim
  encryption because no approved external encryption layer is configured.
- The proposed server job is isolated: no network, read-only application
  filesystem, all Linux capabilities dropped, no new privileges, read-only
  runtime data mount and one dedicated writable backup mount.
- The job requires both `AUTOBOT_SQLITE_BACKUP_ENABLED=true` and
  `AUTOBOT_SQLITE_BACKUP_EXTERNAL_POLICY_APPROVED=true`. Both default to
  `false`; the systemd unit is not installed or enabled by this change.
- The backup directory is ignored by Git; no runtime database or backup payload
  is versioned.

## Evidence

- Targeted resilience/CLI/deployment tests: `45 passed`.
- Full repository suite: `1545 passed, 5 skipped, 1 existing dependency
  deprecation warning`.
- `python -m compileall -q src`: passed.
- `docs/architecture/layer_coverage.json`: parsed successfully.
- `git diff --check`: passed.

## Deployment boundary

The code and disabled unit may be deployed to the VPS. Actual backup creation
and timer installation remain blocked pending an operator decision covering:

1. encrypted off-VPS destination;
2. retention duration and storage budget;
3. restore ownership and recovery runbook.

Until then, the safe default is no scheduled backup rather than an unencrypted
or unbounded local archive.

## Remaining Block 6 work

- validate an approved encrypted off-VPS backup design;
- perform and record a real VPS restore drill from a non-runtime backup;
- continue fail-closed incident, monitoring and reconciliation hardening.
