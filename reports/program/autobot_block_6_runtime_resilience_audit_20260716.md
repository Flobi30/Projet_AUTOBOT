# AUTOBOT Block 6 — Read-only runtime resilience audit (2026-07-16)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

This increment adds a read-only audit of the runtime state database, market-data
freshness, free disk space and explicitly observed WebSocket state. It reports
canonical fail-closed incidents but does not invoke the router, paper engine or
exchange APIs.

## Local validation

- Focused resilience and CLI suite: `54 passed`.
- Full suite: `1559 passed, 5 skipped`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed before commit.
- The only full-suite warning was the existing Starlette/httpx deprecation
  warning; it is unrelated to this change.

## Safety properties

- Missing, unreadable or incompatible SQLite state is classified as
  `SQLITE_CORRUPT` and maps to `HALT`.
- A temporary SQLite busy/locked condition is classified as `SQLITE_LOCKED`
  and maps to a fail-closed order block.
- Missing, invalid, future or stale market observations are classified as
  `DATA_STALE`.
- Low disk capacity is classified as `DISK_FULL`.
- `unknown` WebSocket state is never reported as healthy; it yields
  `PARTIAL_OBSERVABILITY`.
- The command has no order, paper, router, signal-handler or exchange import.
- The audit result is non-authorizing: research-only, no paper capital, no
  live and no order submission.

## VPS validation

Source commit deployed and rebuilt: `d0ce2c52b803b0c8e35ad51c650cebc40716ddea`.

The audit ran in a disposable container with no network, a read-only root
filesystem, no Linux capabilities, and `/opt/Projet_AUTOBOT/data` mounted
read-only.

- `/health`: `healthy`.
- Orchestrator: `running`.
- WebSocket: explicitly observed `connected`.
- Instances: `14`.
- SQLite integrity check: `ok`.
- Latest market observation: `2026-07-16T14:37:21.533645+00:00`.
- Data age at audit: about `116` seconds, below the `300` second threshold.
- Free disk: `62,320,119,808` bytes, above the `2 GiB` minimum.
- Audit status: `RESILIENCE_HEALTHY`; no incidents.

Safety flags remained disabled:

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.

## Remaining work

- Connect this evidence to the future operational monitoring/alerting surface
  without placing business logic in the dashboard.
- Continue failure-injection coverage for API outages, restart recovery and
  reconciliation before any human paper-review dossier can become eligible.
- Persistent encrypted off-VPS backups remain intentionally disabled pending
  an explicit retention destination and policy.
