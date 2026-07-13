# AUTOBOT Block 2 - Funding/Basis Statistical Gate - 2026-07-13

## Decision

`GO` for the research-only statistical gate. The end-to-end workflow remains
correctly blocked at data readiness on the VPS.

## Delivered

- Funding/basis trades now carry spot entry/exit prices, EUR notional, and an
  explicit decomposition of fees, spread, slippage and latency.
- A conversion to the common research trade journal preserves spot-EUR PnL;
  perpetual futures values remain metadata-only directional context.
- After a passing fixed walk-forward, the runner can calculate DSR/PSR proxies
  and deterministic bootstrap/cost-stress diagnostics.
- The statistical gate treats bounded variants, symbols and folds as an
  explicit minimum multiple-testing count.
- A pass returns `KEEP_RESEARCH` only. It cannot enable shadow, paper capital,
  promotion, sizing, leverage or live execution.

## Evidence

- Code commit: `75c608b96eaab0d9bc2c0430e72febd1b5afbd84`.
- Focused local tests: `49 passed`.
- Hermetic VPS research suite: `367 passed`.
- Isolated-image compilation: passed.
- Production container: healthy; `/health` healthy; WebSocket connected;
  14 instances.
- A `full_research` VPS run produced its runtime report and stopped at
  `DATA_CHECK` with `INSUFFICIENT_DATA`.

## Current Blockers

- `BASIS_HISTORY_WAITING`
- `OPEN_INTEREST_HISTORY_WAITING`
- `DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN`

The observed state is safe: no material experiment was recorded, no simulation
was run, and no paper/live/promotion path was called.

## Safety Confirmation

- `LIVE_TRADING_CONFIRMATION=false`
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- Grid remains retired/no-go.

## Next Action

Continue scheduled public derivatives collection. Do not manufacture a holdout
or bypass the point-in-time data gate. In parallel, audit the portfolio/cost/
execution-simulation boundaries for Block 3.
