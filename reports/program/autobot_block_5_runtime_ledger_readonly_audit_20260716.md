# AUTOBOT Block 5 — runtime OMS/ledger read-only audit — 2026-07-16

## Decision

`REWORK / MIGRATION_REVIEW_REQUIRED`.  The legacy runtime ledger is not
eligible to become the canonical OMS/ledger source of truth.  It remains
isolated from the contract-driven research/shadow ledger and must not be
automatically migrated, trusted for promotion, or used to activate paper.

## Method

Two audit commands ran on the VPS inside a disposable container with no
network, a read-only filesystem, no order endpoint and a read-only mount of
`data/autobot_state.db`.  The database hash was identical before and after
both inspections.

## Runtime audit

| Evidence | Result |
|---|---:|
| Orders | 5,811 |
| State transitions | 17,270 |
| Trade-ledger rows | 11,614 |
| Orders missing decision/signal provenance | 125 |
| Transitions missing `from_status` | 17,269 |
| Trades missing canonical traceability | 1,142 |
| Non-terminal orders | 0 |

Verdict: `RECONCILIATION_REQUIRED`.

## Read-only migration plan

The plan deliberately produced no canonical candidates, no reconstructable
fill events and no reconstructable order events.  It returned
`MIGRATION_REVIEW_REQUIRED` with `migration_allowed=false`.

Quarantine reasons include 10,472 unresolved client-order IDs, 17,269 missing
previous states, 587 missing strategy IDs and 555 missing decision IDs.  The
legacy data therefore remains historical/forensic only and cannot affect
strategy evidence, shadow eligibility, paper capital or live execution.

## Existing safe path

The separate research/shadow `ShadowOMSLedger` remains the canonical path for
future contract-bound scenarios.  It is append-only, idempotent, supports
partial-fill/restart/reconciliation tests and is isolated from runtime order
components.  It still accepts shadow intents only.

## Safety confirmation

- The inspection did not write to the database or submit an order.
- No paper capital, live, promotion, sizing or leverage setting changed.
- Grid remains retired/no-go.

## Required future condition

Any future paper-readiness review must start from newly generated,
contract-complete events.  It must not retrofit the legacy rows merely to make
historical statistics look usable.
