# AUTOBOT Block 2 - Runtime Research Reporting - 2026-07-13

## Decision

`GO` - research reporting is now written to the persistent runtime data volume,
not to the versioned source/report tree mounted into the production container.

## Change

- Alpha Hypothesis Runner and scheduler defaults now write to
  `data/research/reports/alpha_hypothesis_runner`.
- A user can still explicitly select a compact versioned report destination;
  this is no longer the automatic runtime path.
- The runner remains research-only. This change does not alter strategy,
  allocation, sizing, paper execution, live execution, promotion, or UI.

## Evidence

- Runtime code commit: `af51db0385bb38b0215c8020d7171f4f8446c727`.
- Local focused suite: `33 passed`.
- Hermetic VPS research suite: `363 passed`.
- Compilation in the isolated test image: passed.
- VPS runner smoke wrote both JSON and Markdown under the runtime data path.
- The funding/basis gate stopped at `DATA_CHECK` with
  `INSUFFICIENT_DATA`: basis/OI history and runtime-parity evidence are still
  insufficient. It did not run a simulation or write any paper/live trade.

## VPS Safety

- Container: healthy; `/health` healthy; WebSocket connected; 14 instances.
- `LIVE_TRADING_CONFIRMATION=false`
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- No critical/live-order log match after deployment.

## Residual Risk

The current VPS worktree contains pre-existing runtime artifacts and a legacy
tracked research-memory file. They were preserved; runtime data must not be
reset or cleaned as part of source deployments.

## Next Action

Keep collecting derivatives forward history. Continue Block 2 with the
statistical-validation and immutable-holdout gates only after the derivatives
readiness gate is satisfied.
