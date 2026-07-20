# AUTOBOT Block 1 — Forward Microstructure Evidence — 2026-07-20

## Decision

**GO, research-only.**  AUTOBOT now captures public Kraken top-of-book
evidence throughout the day in a separate, bounded container.  This improves
cost and capacity research coverage; it does not activate a strategy, shadow
execution, paper capital, promotion, or live trading.

## Implementation

- Implementation commit: `4f4407b459c73613fdd11cdae77e01f47958f9a8`.
- New CLI: `collect-microstructure-forward`.
- New canonical store: UTC `event_time`, `available_time`,
  `ingestion_time`, explicit Kraken base/quote mapping, raw-file SHA-256,
  source IDs, deterministic snapshot fingerprint and quarantine of invalid
  rows.
- Public REST clock skew is normalized forward within a bounded 60-second
  tolerance; data is never available before its exchange event timestamp.
- Non-EUR quotes, implicit conversion, invalid spread/mid values, naïve
  timestamps and a runtime-parity claim are rejected.
- Systemd timer: every 15 minutes, isolated to `data/research` with no
  runtime database, secrets, order router, paper engine, or live path mount.

## Local verification

- `python -m compileall -q src`: passed.
- Focused microstructure/CLI/deployment tests: `58 passed`.
- Full suite: `1731 passed, 6 skipped`.
- `bash -n` on the systemd runner: passed.
- `git diff --check` and secret scan: passed.
- A public BTC/EUR smoke capture completed locally and produced one canonical
  research row with `runtime_parity_proven=false` and
  `execution_eligible=false`.

## VPS verification

- Git checkout and image label: `4f4407b459c73613fdd11cdae77e01f47958f9a8`.
- First controlled capture: `14` snapshots, `14` canonical rows, `0` errors.
- Snapshot ID: `microstructure_v1_be10cf32caa03ae7`.
- The timer is enabled and schedules the next independent capture.
- Runtime after rebuild: container healthy; health endpoint healthy; WebSocket
  connected; 14 instances.
- No critical/traceback/live-order activation log match was observed.

## Safety state

- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`
- `PAPER_TRADING=true` remains an existing legacy configuration only; this
  work did not activate paper capital or route any order.
- Grid remains no-go.

## Remaining limits

- Public REST top-of-book snapshots are sparse research evidence, not full
  order-book replay and not runtime-feed parity proof.
- Capacity estimates must remain conservative until enough forward coverage is
  accumulated across market sessions and stress periods.
- No current strategy has passed the existing net-cost and statistical gates.
