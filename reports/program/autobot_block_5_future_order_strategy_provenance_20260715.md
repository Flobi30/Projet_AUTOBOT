# AUTOBOT Block 5 - Future Order Strategy Provenance

Date: 2026-07-15
Code commit: `86214dcf9ae5ab88117e17bfcb68582cc9a882e0`

## Decision

GO for future-order strategy provenance. The legacy runtime history remains
`RECONCILIATION_REQUIRED`; it was not rewritten, reclassified or used for any
promotion decision.

## Change

- Future persisted orders require a non-empty `strategy_id`.
- `orders.strategy_id` is added through the existing additive schema migration
  path, so existing databases retain their historical data.
- The persisted order state machine rejects a blank strategy before it can
  create an order record; a failed persistence write also stops that lifecycle
  before any later execution path can use it.
- The current runtime signal handler supplies its existing `signal_engine` as
  strategy provenance for future persisted orders.
- This is provenance hardening only: it does not authorize an order, change a
  risk mandate, or connect shadow observations to paper or live execution.

## Validation

- Focused persistence, OMS safety and signal-handler tests: `54 passed`.
- Final disposable Linux release suite: `1584 passed, 4 existing pytest
  warnings` in 70.11 seconds.
- The warnings are pre-existing asyncio marks on synchronous order-router
  tests; no warning was added by this change.
- Contract tests prove that a valid order stores its `strategy_id`, while a
  missing or blank value creates no persisted order and raises before the
  state machine can continue.

## Runtime Evidence

- GitHub, VPS source and running container code are aligned on
  `86214dcf9ae5ab88117e17bfcb68582cc9a882e0`.
- The VPS schema contains `orders.strategy_id` after the additive migration.
- `autobot-v2` is healthy; the orchestrator is running, the WebSocket is
  connected and 14 instances are present.
- No legacy OMS row was modified. Legacy gaps continue to be quarantined by
  the read-only audit and migration planner.

## Safety

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No paper capital, live order, promotion, sizing or leverage change occurred.

## Residual Risk and Next Safe Work

`strategy_id` is now present for future persisted orders, but canonical market
identity (venue, market type, base asset and quote asset) and an immutable
strategy-artifact version are not yet required at this legacy runtime boundary.
The next safe change is to formalize those facts in an isolated, non-executable
shadow `OrderIntent` adapter. It must reject implicit symbol or currency
conversions and remain separate from legacy records and official paper paths.
