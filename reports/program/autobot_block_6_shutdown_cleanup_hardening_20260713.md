# AUTOBOT Block 6 — Shutdown Cleanup Hardening

Date: 2026-07-13  
Code commit: `c45362887fe25e37280622b2fcb262a9b28fec41`

## Decision

GO — the runtime shutdown path now releases process-scoped SQLite persistence
even if another component raises while stopping. This is a resilience correction;
it does not alter strategy, allocation, order, paper-capital, or live behavior.

## Change

- Wrapped `OrchestratorAsync.stop()` cleanup in `try/finally`.
- Kept the original shutdown order on the normal path.
- Moved `close_persistence()` into the `finally` block so a failing background
  task, dispatcher, module, or order-executor shutdown cannot strand aiosqlite
  worker threads before the event loop closes.
- Added a boundary test that injects a failing shutdown component and proves the
  persistence cleanup is still awaited.

## Validation

Local targeted checks:

- `python -m py_compile src/autobot/v2/orchestrator_async.py tests/test_persistence_lifecycle.py`
- `pytest tests/test_persistence_lifecycle.py -q` — 2 passed.
- `pytest tests/test_persistence_lifecycle.py tests/test_orchestrator_async_wiring.py tests/test_orchestrator_services_background_tasks.py tests/test_runtime_sanity.py -q` — 11 passed.
- `git diff --check` — passed.

VPS isolated full suite:

- Disposable Git archive mounted outside the runtime data path.
- `1568 passed, 4 existing pytest warnings` in 70.31 seconds.
- The warnings concern non-async tests carrying an existing asyncio mark in
  `src/autobot/v2/tests/test_order_router.py`; they are unrelated to this change.

## Deployment Evidence

- GitHub and VPS source were aligned on `c45362887fe25e37280622b2fcb262a9b28fec41`.
- `autobot-v2` was rebuilt and recreated successfully.
- `/health` reported `healthy`, orchestrator running, WebSocket connected, and
  14 instances.
- The running container contains the new shutdown `finally` guard.
- Stale `autobot-research-tests` containers from isolated test attempts were
  removed; the production `autobot-v2` container was not touched by that cleanup.

## Safety Confirmation

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No paper-capital activation, live activation, promotion, sizing, leverage, or
  order-path change was made.

## Remaining Work

The 24-layer programme remains deliberately partial. The immediate evidence
blocker is valid multi-pair point-in-time feature history and longer basis/open
interest accumulation; no strategy is eligible for paper capital or live use.
