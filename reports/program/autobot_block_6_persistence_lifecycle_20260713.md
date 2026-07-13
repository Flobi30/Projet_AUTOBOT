# AUTOBOT Block 6 — Persistence Lifecycle and Hermetic Test Completion

## Decision

**GO.** The resilience increment closes process-scoped SQLite workers during
preflight-only runs, normal orchestrator shutdown and isolated test-session
completion. It does not authorize paper capital, live trading, promotions,
orders, leverage or sizing changes.

## Change

- Added an idempotent `close_persistence()` lifecycle function for the global
  `StatePersistence` singleton.
- `OrchestratorAsync.stop()` now releases SQLite worker threads after instance,
  module and order-executor shutdown.
- A preflight-only startup releases its audit persistence before returning.
- The test session closes the singleton after all tests, which prevents leaked
  `aiosqlite` worker threads from keeping Python alive after Pytest reports.

## Evidence

- Code commit: `2f4ee43f44675f21d31cacad8168b9e6f4ebd87a`.
- Focused lifecycle, attestation and governance tests: `26 passed`.
- Full VPS suite in a disposable writable Git archive: `1564 passed` with a
  normal exit status of `0` in approximately 78 seconds.
- The four remaining warnings concern incorrectly applied asyncio markers on
  synchronous legacy router tests; they do not create an execution path and
  are tracked as non-blocking test hygiene.
- Runtime rebuilt and recreated after the change. `/health` reports healthy,
  WebSocket connected and fourteen instances.
- Security configuration after restart: paper execution adapter disabled, live
  confirmation disabled, live strategy router disabled and automatic live
  promotion disabled.

## Residual risk

The persistence lifecycle is now explicit, but the full 24-layer programme
remains `PARTIAL`: current research data is still insufficient to make any
strategy shadow-eligible. This result is intentionally fail-closed.
