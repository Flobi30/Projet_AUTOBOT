# AUTOBOT Block 5 - Legacy OMS/Ledger Migration Plan

Date: 2026-07-15
Code commit: `7f9e947225769069f3cb555b362a379d99fe82b1`

## Decision

GO for the read-only planner. REWORK remains required for the legacy runtime
OMS/ledger itself. No migration is authorized from this evidence.

## Change

- Added `runtime-oms-ledger-migration-plan --state-db`.
- The planner opens SQLite in read-only query-only mode inside a read
  transaction and fingerprints the main database plus any WAL file before and
  after planning.
- It never initializes SQLite, creates output data, imports router/paper/live
  components, starts runtime services, or submits an order.
- It only maps a legacy row when all required facts are explicit. Missing or
  ambiguous provenance, fees, timestamps, order identities, duplicate IDs,
  non-finite fill values and incoherent lifecycle transitions are quarantined.
- Canonical `OrderIntent` reconstruction is deliberately forbidden because the
  legacy runtime table has no verified strategy version or canonical market
  identity.

## VPS Read-only Result

- Source rows: 5,811 orders, 17,270 transitions and 11,614 trade-ledger rows.
- Canonical intent candidates: 0.
- Reconstructable order events: 0.
- Reconstructable fills: 0.
- Quarantined causes:
  - 17,269 transitions missing `from_status`;
  - 1 incoherent legacy transition;
  - 555 trade rows missing a decision ID;
  - 587 trade rows missing a strategy ID;
  - 10,472 fills without a uniquely resolvable client order ID.
- The database snapshot fingerprint was identical before and after planning.
- Result: `MIGRATION_REVIEW_REQUIRED`, with
  `migration_allowed=false`, `paper_capital_allowed=false`,
  `live_allowed=false` and `order_submission_attempted=false`.

## Validation

- Contracts, CLI, runtime audit, planner and hermetic OMS tests: `50 passed`.
- Final full Linux suite in the disposable, read-only test container:
  `1580 passed, 4 existing pytest warnings` in 69.49 seconds.
- The warnings are existing asyncio marks on synchronous order-router tests;
  they are unrelated to this change.
- A local Windows full-suite attempt still exposes known platform/tooling
  failures outside this change; the isolated Linux result is the release gate.

## Deployment and Safety

- GitHub, VPS source and the running container code are aligned on
  `7f9e947225769069f3cb555b362a379d99fe82b1`.
- `autobot-v2` is healthy; the orchestrator is running, WebSocket is connected
  and 14 instances are present.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No critical or live-order log was observed during deployment checks.

## Next Safe Work

Do not mutate the legacy runtime ledger in place. The next OMS work must add a
new canonical, append-only future-event writer behind explicit contracts and
tests, then collect clean shadow evidence. Legacy records remain quarantined
unless a separate, human-approved backup and rollback migration design proves
their missing provenance can be resolved without inference.
