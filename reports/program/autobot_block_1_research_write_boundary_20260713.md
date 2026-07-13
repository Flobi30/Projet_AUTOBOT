# AUTOBOT Block 1 — Research Write Boundary

Date: 2026-07-13  
Code commit: `45fba251e0d918e5618c7cd8aec0ee74d5512814`

## Decision

GO — public data-collection jobs can now write only below `data/research`.
They no longer receive a writable mount for the runtime state database or any
official paper/live ledger.

## Change

- Restricted the daily OHLCV/feature collector writable mount from
  `data/` to `data/research/`.
- Applied the same restriction to the 15-minute and daily Kraken Futures
  derivatives collectors.
- Kept the capability scanner's access to the runtime state database read-only.
- Added deployment tests that reject a future writable `data:/app/data` mount.

## Validation

- Shell syntax checks passed for both collection scripts.
- Collection/deployment/daily-runner suite: `8 passed`.
- `git diff --check` passed.

## VPS Smoke

- VPS source aligned to `45fba251e0d918e5618c7cd8aec0ee74d5512814`.
- Manual public derivatives collector completed successfully with snapshot
  `kraken_futures_a06d3461db9028f2`.
- The collector reported public data only and no private endpoint, order,
  paper-capital, live, promotion, shadow activation, sizing, leverage, UI, or
  runtime order path.
- `autobot-v2` remained healthy with the orchestrator running, WebSocket
  connected, and 14 instances.

## Safety Confirmation

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

## Remaining Work

OHLCV and feature snapshots are point-in-time correct but still retained per
run rather than compacted into a continuous history. Basis and open-interest
history continue to accumulate and remain data-gated. No strategy is eligible
for paper capital or live use.
