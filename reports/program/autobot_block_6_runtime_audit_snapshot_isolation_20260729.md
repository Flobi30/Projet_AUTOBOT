# AUTOBOT Block 6 — Runtime SQLite Audit Snapshot Isolation (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the read-only resilience audit now performs expensive SQLite
integrity and freshness checks against an ephemeral backup snapshot rather than
the active runtime database.

## Finding

The incident runbook calls for snapshot-based diagnostics during SQLite
contention, but `audit_runtime_resilience()` previously opened
`autobot_state.db` directly and ran `PRAGMA integrity_check` there.  On a busy
runtime database that can unnecessarily prolong a read transaction and add
contention to persistence paths.

## Change

- A temporary directory contains a SQLite Backup API snapshot created from a
  read-only source connection.
- Integrity and market-data freshness inspection run only on that snapshot.
- The temporary snapshot is cleaned in all normal audit paths.
- A busy or locked snapshot operation remains a `SQLITE_LOCKED` fail-closed
  incident; no silent fallback reads the active database.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_runtime_resilience_audit.py \
  tests/research/test_resilience_readiness.py \
  tests/test_persistence_db_reliability.py \
  tests/test_persistence_lifecycle.py \
  tests/test_cold_restart_recovery_interlock.py \
  tests/test_v2_cli.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted Block 6 regression: `135 passed`;
- diff check: PASS.

The new tests prove that a real snapshot is removed after inspection without
mutating the source database, that the audit reads the snapshot rather than the
runtime source, and that a temporary lock returns a non-normal fail-closed
result.

## Safety and deployment

- read-only research resilience audit only; no router, executor, paper engine
  or exchange client import added;
- no VPS/SSH action while Hetzner is unavailable;
- no paper capital, live execution, promotion, sizing or leverage change;
- Grid remains retired from execution.

## Residual risk

The SQLite Backup API still needs controlled VPS evidence under the actual
runtime write rate.  The local change avoids direct diagnostic scans of the
active database, but it cannot substitute for the deferred runtime smoke after
the Hetzner maintenance/payment issue is resolved.
