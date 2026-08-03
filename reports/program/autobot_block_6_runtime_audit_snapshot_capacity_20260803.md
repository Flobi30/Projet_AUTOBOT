# AUTOBOT Block 6 — Runtime Audit Snapshot Capacity — 2026-08-03

## Decision

`GO` after correcting an audit-only false classification.  The runtime remains
research/shadow-only; no paper capital, live trading, order submission,
promotion, sizing or strategy behaviour changed.

## Finding

The isolated runtime-resilience audit reported `SQLITE_CORRUPT` while the VPS
state database passed `PRAGMA integrity_check` and exposed the expected
`market_price_samples` table.  Direct reproduction in the same restricted
container showed the actual exception during the read-only SQLite Backup API:

```text
sqlite3.OperationalError: database or disk is full
```

The runtime database was approximately 136 MiB but the audit container had a
64 MiB `/tmp` filesystem.  This was a temporary snapshot-capacity failure, not
database corruption.

## Correction

The audit service now sizes its private temporary filesystem from the current
runtime database: three times the database size plus 64 MiB headroom, capped
at 1 GiB.  Its cgroup memory limit includes separate headroom for the audit
process.  The source database remains mounted read-only and the audit still
has no network, secret, router or order capability.

An SQLite `OperationalError` containing `disk is full` or `no space left` is
now classified as the existing fail-closed `DISK_FULL` incident.  It is no
longer misreported as `SQLITE_CORRUPT`.

## Validation required for deployment

- focused runtime-resilience tests, including snapshot-capacity classification;
- full test suite, compilation, shell syntax and diff checks;
- VPS controlled rebuild and a fresh isolated resilience audit;
- deployment evidence proving the programme execution lock and all paper/live
  locks remain active.
