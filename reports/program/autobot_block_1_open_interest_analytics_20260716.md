# AUTOBOT Block 1 — Official Open-Interest Analytics Collection

## Decision

**GO — research-data capability only.**

AUTOBOT can now collect a bounded, public Kraken Futures open-interest history from the official market-analytics endpoint.  This is a separate canonical dataset: a current ticker snapshot can no longer be described as an open-interest history.

## Scope

- Public Kraken Futures market-data endpoint only: `/api/charts/v1/analytics/{symbol}/open-interest`.
- Explicit start timestamp, bounded end and page count, official interval validation, UTC timestamps, raw-response retention, deterministic deduplication and atomic history compaction.
- The canonical rows use bucket-close availability semantics and retain `event_time`, `available_time` and `ingestion_time`.
- `open_interest_change_24_pct` is now version `2.0.0`, sourced from canonical open-interest history rather than ticker snapshots.
- The capability scanner reports the source and preserves the distinction between current OI and historical OI.

## Evidence

- Unit and integration-focused suite: `79 passed`.
- Local isolated public smoke on BTC and ETH, 2026-07-06 through 2026-07-16:
  - 482 canonical analytics observations;
  - zero collection errors;
  - `open_interest_history_source=kraken_futures_market_analytics`;
  - deterministic feature materialization: 482 values, 434 ready, 48 waiting for the 24-period lookback, parity true.
- The smoke returned `paper_capital_allowed=false`, `live_allowed=false` and `promotable=false`.

## Safety and limitations

- The collection is opt-in; the scheduled forward collector remains unchanged.
- No order, private Kraken endpoint, paper-capital path, promotion, shadow activation, sizing or leverage path is imported or called.
- Open-interest availability does not make `funding_basis` tradable.  Basis history, out-of-sample validation, cost validation and every existing promotion gate remain mandatory.
- Layer 1 and layer 5 remain `PARTIAL` until VPS evidence and the wider runtime-parity gates are complete.

## Next gate

Deploy this collector, run a bounded VPS smoke on BTC/ETH, re-scan capabilities, and keep every strategy in research/shadow-only status.
