# AUTOBOT Block 1 — Open-Interest Analytics VPS Validation (2026-07-16)

## Decision

**GO — research data only.** The public Kraken Futures open-interest collector is deployed and produces canonical, point-in-time data. This evidence does **not** make `funding_basis` runnable, does not prove runtime parity from a backfill, and does not enable shadow activation, paper capital, promotion, or live trading.

## Revision and scope

- Implementation revision validated on VPS: `d00ffd2962b859141c8db4334bd18794f34b97f0`.
- Scope: bounded public Kraken Futures Market Analytics `open-interest` history for BTC and ETH only.
- Interval and window: 1 hour, `2026-07-06T00:00:00Z` to `2026-07-16T00:00:00Z`.
- No private endpoint, exchange order endpoint, API key, strategy runner, paper execution adapter, or runtime order path was invoked.

## VPS evidence

The collector wrote its runtime report to `data/research/reports/kraken_futures_derivatives/`, rather than the repository documentation directory. The first attempt exposed that the former default report directory was read-only to the non-root container user; revision `d00ffd2` corrected the default path without expanding VPS permissions.

| Check | Result |
| --- | --- |
| Canonical open-interest observations | 482 |
| Source | `kraken_futures_market_analytics` |
| Canonical duplicates / collector errors | 0 / 0 |
| Markets | `PF_XBTUSD`, `PF_ETHUSD` |
| Feature values materialized | 482 |
| Feature values ready after 24-hour lookback | 434 |
| Values correctly waiting for lookback | 48 |
| Quote conversion | None; no USD/EUR implicit conversion |
| Point-in-time materialization before ingestion | `DATA_MISSING` as expected |
| Point-in-time materialization after ingestion | `READY`, with `runtime_parity_proven=false` as expected for backfilled rows |

The feature uses the explicit `open_interest_history` dataset and feature version `2.0.0`. Backfilled observations retain their ingestion/availability timing and must not be represented as proof of a real-time runtime path.

## Quality and safety checks

- Local focused collector/CLI tests after the report-path correction: **56 passed**.
- Local full regression before deployment: **1,573 passed, 5 skipped**.
- Local compilation and diff whitespace checks: passed.
- VPS health: healthy; orchestrator running; WebSocket connected; 14 instances.
- VPS observed resources: 5.80% CPU, 87.93 MiB / 3 GiB memory; root filesystem 14 GiB / 75 GiB used.
- Recent logs: no traceback, critical error, live-order, or Kraken-order match.
- Safety configuration remains disabled: paper execution adapter, live confirmation, live strategy router, automatic promotion, and instance split executor.

## Remaining constraints

1. This bounded backfill establishes data quality only. A forward collector must accumulate observations before any runtime-parity claim.
2. Open-interest history remains short and limited to BTC/ETH in this validation; it is not sufficient for an alpha decision.
3. `funding_basis` remains `WAITING_FOR_MORE_DATA`; `liquidation_cascade` remains data-missing.
4. The next Block 1 task is forward-only collection scheduling and data-freshness monitoring, followed by evidence that a feature produced at runtime matches an independently reproduced batch value.
