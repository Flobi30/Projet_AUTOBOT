# AUTOBOT Block 6 — Isolated runtime resilience monitoring (2026-07-16)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

The runtime-resilience audit is now collected by an isolated operational timer.
It is monitoring evidence only: it has no router, paper engine, exchange or
secret access and cannot authorize a strategy, capital, paper trading or live
trading.

## Implementation

- Source commit: `5d481b87facf1252c52241a6c662177a8228d23a`.
- A five-minute systemd timer runs a disposable container with no network,
  read-only root filesystem, no capabilities and the AUTOBOT data directory
  mounted read-only.
- The host wrapper observes the authenticated runtime health endpoint only to
  supply explicit WebSocket evidence; the container reads no environment file
  and has no exchange credentials.
- The only output is atomically replaced at
  `data/research/reports/runtime_resilience/latest.json`.
- `INCIDENTS_DETECTED` or `PARTIAL_OBSERVABILITY` causes the oneshot service
  to fail visibly in systemd; it does not change runtime trading behavior.

## Validation

- Focused audit/deployment/CLI tests: `56 passed`.
- Full suite: `1561 passed, 5 skipped`.
- `python -m compileall -q src`: passed.
- Shell syntax and systemd unit verification: passed on the VPS.
- First manual monitor run: `RESILIENCE_HEALTHY`.
- First systemd monitor run: `Result=success`, `ExecMainStatus=0`.
- Timer is `enabled` and `active`; next cadence is five minutes.

## VPS evidence

- `/health`: `healthy`.
- Orchestrator: `running`; WebSocket: `connected`; instances: `14`.
- SQLite integrity: `ok`.
- Data age on scheduled run: about `83` seconds, below `300` seconds.
- Free disk: about `62.3 GB`, above the `2 GiB` lower bound.
- No incidents and fail-closed action `NORMAL`.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`.
- `LIVE_TRADING_CONFIRMATION=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`.

## Remaining work

- Add explicit external alert routing only after selecting a non-secret alert
  destination and escalation policy.
- Continue failure-injection and recovery testing for API loss, WebSocket loss,
  container restart and reconciliation before a human paper-review dossier.
