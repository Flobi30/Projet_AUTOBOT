# AUTOBOT Block 6 — Legacy state and research-outcome SQLite retry

## Scope

Local-only continuation of B6 persistence resilience. This patch applies the
already-established shared SQLite retry/rollback policy to remaining direct
writes in `StatePersistence`.

## Change

- `cleanup_orphaned_instances()` uses the shared instance-state write lock and
  bounded retry policy.
- `record_instance_lineage()` uses the same policy, preserving the lineage
  audit trail under temporary SQLite contention.
- `record_trade()` uses the same policy for legacy compatibility rows.
- `upsert_signal_outcome()` uses the orders/decision-ledger shared write lock
  and bounded retry policy.

No strategy, outcome calculation, position status, allocation, order path,
paper-capital policy, or live flag changed.

## Evidence

Commands run locally:

```text
python -m py_compile src/autobot/v2/persistence.py
$env:PYTHONPATH='src'; python -m pytest \
  tests/test_persistence_db_reliability.py \
  tests/test_persistence_lineage_retention.py \
  tests/test_persistence_lifecycle.py \
  tests/test_decision_learning.py -q
```

Result: **38 passed**.

Added regression coverage injects one temporary `database is locked` error for
each write family and verifies the write retries once with a rollback before
the successful commit.

## Safety and limits

- No private Kraken endpoint, order, shadow run, paper-capital action,
  promotion, sizing/leverage change, or live flag was used or changed.
- The legacy `trades` table remains compatibility data; the canonical official
  ledger rules are unchanged.
- The retry policy is bounded and fails closed by returning the existing error
  result when SQLite remains unavailable.

## VPS status

The Hetzner VPS is unavailable for the provider/account maintenance reported by
the user. No remote connection, deployment, rebuild, restart, or runtime data
operation was attempted.

## Decision

**GO (local only).** Ready for commit and GitHub push. Linux/VPS evidence is
deferred until service restoration.
