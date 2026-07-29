# AUTOBOT Block 6 — Research-memory SQLite retry

## Scope

Local-only resilience hardening for the append-only research-memory store.
The store records experiment/research observations only; it does not route
orders, allocate capital, or alter strategy runtime policy.

## Change

- Research-memory SQLite connections now use WAL and the configured busy
  timeout.
- Append operations use a bounded exponential retry for transient `locked` or
  `busy` errors.
- Each attempt owns a short connection/transaction, rolls back on failure, and
  closes the connection before retrying.
- The `(run_id, content_hash)` idempotency key resolves uncertain commit
  acknowledgement safely: after a transient failure, an already-present key is
  treated as a successful durable append rather than a false negative.
- A persistent busy/locked error is surfaced; it is never reported as a saved
  research observation.

## Evidence

Commands run locally:

```text
python -m py_compile src/autobot/v2/research/research_memory_store.py
$env:PYTHONPATH='src'; python -m pytest \
  tests/research/test_alpha_hypothesis_scheduler.py \
  tests/research/test_bounded_research_coordinator.py \
  tests/research/test_data_capability_scanner.py \
  tests/research/test_research_retry_eligibility.py -q
```

Result: **56 passed**.

Regression tests cover a temporary lock followed by an existing idempotency key
and a persistent lock that must remain visible to the caller.

## Safety

- Research-only invariants remain validated: paper capital, live and promotion
  flags are forbidden in stored records.
- No strategy execution, shadow run, paper-capital action, private Kraken API,
  order endpoint, sizing/leverage change or dashboard change occurred.

## VPS status

Hetzner remains unavailable for the reported provider/account maintenance. No
SSH, deployment, rebuild, restart, remote database action or data collection
was attempted.

## Decision

**GO (local only).** The patch is ready for GitHub. Linux/VPS runtime evidence
must be collected after service restoration.
