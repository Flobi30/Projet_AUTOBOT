# AUTOBOT Block 1 — Automatic Daily Capability Scan

## Decision

**GO.** Every successful public-data collection will now finish with a
research-only capability report. This is observability for the Alpha Lab; it
does not run a strategy or alter execution.

## Change

The systemd collection script now performs two separate container jobs:

1. public Kraken data collection and canonical feature materialization;
2. a read-only, network-disabled capability scan of the resulting research
   data.

The scan writes only its compact report into the existing daily research report
directory. It receives no secret, order route, dashboard, runtime database
write permission, paper permission or live permission.

## Verification

- Unit and scanner/daily-runner tests: `15 passed`.
- VPS shell syntax validation: passed.
- VPS smoke executed the exact read-only capability command successfully.
- Smoke report: `daily_capability_smoke_20260713.json`.
- The smoke confirmed `paper_capital_allowed=false` and `live_allowed=false`.

## Result

The current scanner keeps rejected OHLCV configurations blocked, keeps
funding/basis waiting for more basis history, and keeps liquidation research
blocked for lack of liquidation events. This is the expected fail-closed state.
