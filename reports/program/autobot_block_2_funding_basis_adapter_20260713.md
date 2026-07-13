# AUTOBOT Block 2 - Funding/Basis Research Adapter - 2026-07-13

## Decision

`GO` for the bounded funding/basis adapter in research only.

The adapter is installed but data-gated.  It cannot currently run a smoke
simulation on the VPS because basis/OI forward history remains insufficient.
It has no paper, live, order-routing, or promotion capability.

## Delivered

- `funding_basis_research_adapter` consumes point-in-time derivatives feature
  snapshots and mapped spot-EUR OHLCV.
- The perpetual USD series provides directional context only.  Every simulated
  gross/net result is calculated from the mapped spot-EUR OHLCV series; no
  implicit USD/EUR price conversion exists.
- Entry uses the next spot bar after the derivatives features were available.
- Variants are bounded by the existing template (`funding_percentile`,
  `max_hold_hours`) and evaluated in template order, never selected by best
  historical PnL.
- Costs are applied through the shared research cost model.  A no-loss sample
  does not receive an infinite PF.
- The runner, scheduler and template now recognize the adapter, while all
  paper/live/promotion flags remain forced false.
- A fixed-template walk-forward now evaluates sequential non-overlapping
  out-of-sample windows. A signal, entry and exit must all be inside the
  relevant test window; no fold can select parameters from its own future.

## Evidence

- Adapter baseline: `fe07e16f193301732e6a00a4777fb707a695c8d2`
- Walk-forward gate: this report is versioned with the implementation commit.
- Focused hermetic tests: `46 passed`
- Full hermetic research suite: `360 passed`
- Compilation in the isolated test image: passed
- Production container after deployment: healthy; `/health` healthy;
  orchestrator running; WebSocket connected; 14 instances.
- End-to-end VPS research smoke:
  - spot feature snapshot: `features_v1_efb1946a8298900e`;
  - derivatives snapshot: `WAITING_FOR_MORE_DATA`;
  - runner result: `INSUFFICIENT_DATA` at `DATA_CHECK`;
  - no adapter simulation, order, paper write or promotion was performed.

## Safety Confirmation

- `LIVE_TRADING_CONFIRMATION=false`
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- The adapter imports no runtime router, paper engine, order handler or Kraken
  private client.
- Grid remains retired/no-go.

## Remaining Gates

- Basis/OI history must reach the configured coverage before the adapter can
  run against VPS data.
- Spot canonical data still has unknown ingestion times, so it cannot prove
  runtime shadow parity; those data are usable only for bounded historical
  research.
- A passing net-cost walk-forward still requires stress/Monte Carlo, holdout
  and explicit human review before any shadow consideration.

## Next Action

Add the statistical-validation path after the data gate turns green. Until the
forward data gate turns green, the correct automated outcome is to keep
collecting.
