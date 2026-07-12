# AUTOBOT Block 2 — Derivatives Readiness Gate — 2026-07-12

## Decision

`GO` for explicit derivatives research readiness.  `funding_basis` remains
blocked from an alpha smoke test until its data history and a dedicated,
research-only adapter both exist.

## Delivered

- A derivatives snapshot now has a small, typed readiness view that rejects:
  - a non-derivatives manifest;
  - an unverified same-quote basis contract;
  - any paper/live/promotion permission;
  - an invalid data status.
- The Alpha Hypothesis Runner consumes the spot and derivatives snapshots
  before its funding/basis data gate.  It distinguishes `DATA_MISSING` from
  `INSUFFICIENT_DATA` / `WAITING_FOR_MORE_DATA`.
- A ready input bundle can pass only the research data gate.  The next smoke
  gate stops at `funding_basis_adapter_not_implemented`; it cannot create a
  signal, shadow write, paper order, or promotion.
- The scheduler now reports derivatives history as `WAITING_FOR_MORE_DATA`
  instead of claiming generic missing data.
- Point-in-time materialization now fails closed when `ingestion_time` is
  absent or later than the requested `as_of_time`.

## Evidence

- GitHub / VPS commit: `e7f7f61e344281c2e0440e12be2ef4b2884b29ca`
- Targeted research tests: `55 passed`
- Full isolated research suite: `355 passed`
- Python compilation in the isolated image: passed
- VPS materialization smoke, `2026-07-12T18:27:16Z`:
  - funding history: 53,980 rows, from 2025-07-02 to 2026-07-12;
  - basis/ticker histories: 288 rows each, starting 2026-07-12;
  - feature snapshot: `derivatives_features_v1_0d8061948b3fda44`;
  - result: `WAITING_FOR_MORE_DATA`;
  - blockers: `BASIS_HISTORY_WAITING`,
    `OPEN_INTEREST_HISTORY_WAITING`,
    `DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN`;
  - 16 rows lacking an explicit ingestion time were excluded, not inferred.
- Runtime after deployment: container healthy; `/health` healthy; orchestrator
  running; WebSocket connected; 14 instances.

## Safety Confirmation

- `LIVE_TRADING_CONFIRMATION=false`
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No private API, order path, paper capital, live activation, promotion,
  sizing, leverage, dashboard, or grid change was made.

## Remaining Gates

1. Accumulate the configured forward basis/OI history.
2. Preserve explicit ingestion times for all canonical derivatives rows.
3. Build a dedicated research-only funding/basis adapter with an explicit
   derivative-signal-to-spot-return mapping.  It must never perform an
   implicit USD/EUR price conversion.
4. Run its bounded net-cost smoke, walk-forward, stress and holdout stages
   only after the data gate is green.

## Next Action

Implement the research-only adapter contract and its hermetic tests while the
forward data continues to accumulate.  It will remain `ADAPTER_MISSING` at
runtime until that work is complete and all research gates are satisfied.
