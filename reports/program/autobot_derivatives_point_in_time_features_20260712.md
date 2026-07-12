# AUTOBOT — Derivatives Point-in-Time Features, 2026-07-12

## Decision

**GO — derivatives features are reproducible research artifacts; strategy validation remains blocked.**

The new `DERIVATIVES_POINT_IN_TIME` snapshot contract connects canonical public derivatives histories to experiment provenance without creating an executable strategy, an order, paper capital or live behavior.

## Delivered contract

- An explicit `as_of_time` excludes future or not-yet-available rows.
- Every snapshot fingerprints the selected funding, basis and open-interest histories plus the explicit perpetual-contract mapping.
- Features retain a `kraken_futures` perpetual market identity and USD quote. No implicit conversion to AUTOBOT EUR spot symbols is permitted.
- Basis accepts only `MARK_INDEX_SAME_QUOTE`; unverified basis data is excluded.
- Historical funding rows missing a quote field are completed only from the explicit collector manifest mapping. A contradictory mapping is excluded.
- Missing or unknown temporal status fails closed for runtime parity.
- A manifested experiment may bind a derivatives snapshot materially alongside a spot feature snapshot. Local manifest paths are excluded from the experiment identity, preventing artificial trial duplication after a file move.
- The CLI remains research-only: `materialize-derivatives-feature-snapshot`.

## VPS evidence

- GitHub/VPS/runtime code commit: `5d2498582d8e6c689788f5e666889cd5a61c9fbf`.
- Container healthy; orchestrator running; WebSocket connected; 14 instances.
- Derivatives timer active and collecting public snapshots every 15 minutes.
- Latest smoke snapshot: `derivatives_features_v1_a4f60465f1a1fae7`.
- Funding: 53,668 canonical rows, 2025-07-02 through 2026-07-10.
- Basis/OI: 158 rows each at smoke time, accumulated from 2026-07-10.
- Snapshot state: `WAITING_FOR_MORE_DATA`.
- Required blockers: `BASIS_HISTORY_WAITING`, `OPEN_INTEREST_HISTORY_WAITING`, `DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN`.

## Validation

- Focused derivatives/provenance tests: 10 passed.
- Full research test suite in an isolated network-disabled test container: 347 passed.
- Compilation of `src/`: passed.
- The test image now copies only the compact, versioned historical reports required for deterministic scheduler-memory tests.

## Safety evidence

- `LIVE_TRADING_CONFIRMATION=false`.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`.
- `STRATEGY_ROUTER_LIVE_ENABLED=false`.
- `COLONY_AUTO_LIVE_PROMOTION=false`.
- `PAPER_DYNAMIC_CAPITAL_REBALANCE_ENABLED=false`.
- No paper capital, live order, promotion, sizing or leverage change was made.

## Next gate

The data archive must reach the seven-day/96-observation coverage rule for every mapped perpetual before the derivatives snapshot can become `READY`. Even then, its historical funding backfill does not prove runtime parity, so it cannot make a strategy shadow-eligible without independent forward collection and validation.
