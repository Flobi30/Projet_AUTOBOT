# AUTOBOT Block 5 — OMS/Ledger Cutover Evidence

## Decision

`GO — continue Block 5 hardening only.`

The runtime database is structurally healthy, but historical OMS/ledger rows
cannot satisfy the canonical contracts. They remain quarantined. This work
does not migrate, rewrite, reconcile, route, promote, or execute any order.

## Scope

- Add a read-only `--cutover-at` view to `runtime-oms-ledger-audit`.
- Keep the all-history verdict intact: legacy debt is never silently ignored.
- Report whether rows at or after an explicit UTC cutover satisfy current
  `decision_id`, `signal_id`, `strategy_id`, transition and execution-mode
  provenance contracts.
- Require timezone-aware cutovers and preserve the runtime SQLite file exactly.

## VPS Baseline Evidence

The read-only audit was run against the active runtime state database before
this code change.

| Evidence | Result |
|---|---:|
| Orders | 5,811 |
| Order transitions | 17,270 |
| Trade-ledger rows | 11,614 |
| Legacy orders missing decision/signal provenance | 125 |
| Legacy transitions missing `from_status` | 17,269 |
| Legacy trades missing canonical traceability | 1,142 |
| Read-only audit changed the database | No |
| Automatic migration allowed | No |

The non-executable migration planner found no defensible canonical order
intent, order-event or fill-event reconstruction candidate in that legacy
population. It therefore remains `MIGRATION_REVIEW_REQUIRED` rather than
inventing provenance.

Using the P0 boundary `2026-07-01T00:00:00+00:00`, the post-cutover ledger had
2,996 rows and zero missing `decision_id`, `signal_id`, `strategy_id` or
`execution_mode` fields. There was no new persisted order or transition in
that interval. This is traceable research/shadow ledger evidence only; it is
not a paper-capital or live readiness claim.

## Implementation

`runtime-oms-ledger-audit --cutover-at <UTC ISO-8601>` now returns a distinct
`cutover_evidence` object:

- `POST_CUTOVER_TRACEABLE_EVIDENCE` for attributable rows after the boundary;
- `POST_CUTOVER_CONTRACT_VIOLATION` when a newer row is incomplete;
- `NO_POST_CUTOVER_CONTRACT_EVIDENCE` when no newer row exists;
- `CUTOVER_EVIDENCE_UNAVAILABLE` when the database/schema cannot support the
  comparison.

The all-history audit remains `RECONCILIATION_REQUIRED` while legacy rows are
incomplete. The cutover result cannot turn the historical verdict green.

## Validation

```text
$env:PYTHONPATH='src'; python -m pytest \
  tests/research/test_runtime_oms_ledger_audit.py \
  tests/research/test_runtime_oms_ledger_migration_plan.py \
  tests/research/test_oms_ledger.py \
  tests/test_persistence_db_reliability.py -q
26 passed

python -m py_compile src/autobot/v2/research/runtime_oms_ledger_audit.py src/autobot/v2/cli.py
git diff --check
```

The test suite covers legacy debt, traceable post-cutover rows, post-cutover
violations, missing databases, naive timestamps and the no-execution import
boundary.

## Safety Invariants

- Research/shadow only.
- No paper capital, live, auto-promotion, sizing or leverage change.
- No private endpoint, API key, secret or order route used.
- No runtime database migration or write.
- Grid remains retired and outside the official ledger path.

## Residual Risk and Next Action

The legacy runtime OMS tables cannot be used to reconstruct canonical
`OrderIntent` evidence. The next Block 5 task is to fail closed on any future
runtime persistence attempt that lacks canonical decision, signal, strategy,
cost and execution-mode provenance, while preserving the legacy database as
historical evidence.
