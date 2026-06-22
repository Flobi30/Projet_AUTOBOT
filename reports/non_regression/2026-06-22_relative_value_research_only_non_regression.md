# Relative Value Research-Only - Non-Regression (2026-06-22)

## Verdict

PASS_WITH_WARNINGS

## Scope

Added an isolated Kraken Spot, long-only Relative Value replay. It is reachable
only through the research CLI command `relative-value-portfolio-replay`.
It is not imported by the runtime strategy factory, router, paper executor,
order executor, dashboard, or promotion workflow.

## Trading Safety

- Every generated signal has `side=buy`; references are statistical inputs and
  are never submitted as orders.
- The replay uses `RiskManagerV2` with leverage disabled, one position per
  target symbol, global/symbol exposure limits, cooldowns, daily-loss limits,
  and a drawdown stop.
- `ExecutionCostModel`, `TradeJournal`, and `MetricsEngine` are reused for
  conservative cost accounting and reproducible artifacts.
- Both `paper_current_taker` and `research_stress` profiles are mandatory.
- `live_promotion_allowed=false`; no paper/live runtime, sizing, risk flag,
  promotion, split, or Kraken private endpoint was changed.

## First Frozen-Parameter Run

Dataset: Kraken OHLCV daily snapshot `2026-06-08`, 15-minute bars, capital
`500 EUR`, three fixed relationships: ADA/XRP, LINK/DOT, AVAX/SOL.

| Profile | Trades | Net PnL EUR | PF | Max DD % | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| paper_current_taker | 14 | -14.6967 | 0.2835 | 4.3304 | NO GO |
| research_stress | 14 | -15.1406 | 0.2730 | 4.4164 | NO GO |

The run is below the 30-trade minimum and fails positive-net-PnL and profit
factor gates. It is therefore research-only and explicitly not promotable.
Compared to the existing high-conviction portfolio replay (`+18.137 EUR`, nine
trades, also insufficient evidence), Relative Value was lower by `32.834 EUR`
on this short sample.

## Validation

- `python -m compileall -q src`: passed.
- Focused AUTOBOT regression suite: `229 passed`.
- `docker compose config -q`: passed.
- `git diff --check`: passed.

## Remaining Warnings

- The local environment does not provide `statsmodels`; rolling OLS/correlation
  and z-score were measured, while Engle-Granger is marked unavailable rather
  than silently assumed.
- OHLCV volume is only a liquidity proxy. Bid/ask and depth remain necessary
  before any future paper-candidate review.
- The current sample is short. The NO GO conclusion must be retained until a
  longer, fixed-parameter Kraken history can be evaluated.

## Controlled Deployment Verification

Runtime code commit `1dfb4d8` was deployed to the VPS. The Docker container is
healthy; `/health` reports an active orchestrator, connected WebSocket, and 14
instances. All 14 instances remain `ObservationOnlyStrategyAsync`.

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- Router remains paper-only with official paper execution and live promotion
  disabled.
- No critical runtime error or live-order log was observed.
- The new `relative-value-portfolio-replay` CLI is available inside the image
  with AUTOBOT's normal `PYTHONPATH`.
