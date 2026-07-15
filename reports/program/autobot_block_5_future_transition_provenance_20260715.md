# AUTOBOT Block 5 - Future Order Transition Provenance

Date: 2026-07-15
Code commit: `704c0e6bf717b694d31078c922fe6f8a993b209b`

## Decision

GO for the future-transition evidence fix. Existing OMS/ledger history remains
`RECONCILIATION_REQUIRED` and is not migrated or modified.

## Change

- `OrderRepository.transition_order_state()` now reads the current persisted
  order state before mutating the order.
- A new transition records that state in `from_status` in the same serialized
  write boundary as the order update.
- A transition for an unknown order, or an order with no prior state, is
  rejected without creating an orphan transition row.
- The write keeps bounded SQLite retry behavior and changes neither order
  routing policy nor paper/live permissions.

## Validation

- Persistence lifecycle, reliability and OMS-audit/planner tests: `14 passed`.
- Final full Linux suite: `1581 passed, 4 existing pytest warnings` in
  70.24 seconds.
- The new test proves `NEW -> SENT` persists `from_status=NEW`, while an
  unknown order creates no transition.

## Runtime Evidence

- GitHub, VPS source and running container code are aligned on
  `704c0e6bf717b694d31078c922fe6f8a993b209b`.
- `autobot-v2` is healthy; orchestrator running, WebSocket connected, 14
  instances.
- A fresh read-only legacy audit is unchanged: 17,269 historical transitions
  still lack `from_status`; this fix does not rewrite them.

## Safety

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No paper capital, live order, promotion, sizing or leverage change occurred.

## Next Safe Work

Propagate verified strategy and market provenance into the future shadow order
intent boundary. This must remain separate from legacy data and must preserve
the risk gate before any executable command can exist.
