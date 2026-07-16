# AUTOBOT Block 1 — Same-Quote Basis History — 2026-07-16

## Decision

`GO` for a **research-data capability only**.  This change does not activate
an alpha, shadow execution, paper capital, promotion, sizing, leverage, or
live trading.

## Delivered

- Added an opt-in, date-bounded public Kraken Futures Charts backfill.
- Hard-limited every collection by symbol count, page count, candle count and
  optional UTC start/end bounds.
- Derived historical basis only from aligned closed `mark` and `spot`
  reference candles of the same futures contract, timeframe and timestamp.
- Rejected implicit quote-currency mixing; a USD/EUR comparison cannot create
  a basis row.
- Kept the normal forward collector unchanged unless an explicit backfill
  start timestamp is supplied.
- Prevented Futures candle files from being treated as spot execution OHLCV
  by the data-capability scanner.
- Corrected the derivatives-quality label so an accumulated historical basis
  series is not reported as a current-only smoke snapshot.

## VPS Research Smoke

The public, isolated collector ran on the VPS with BTC and ETH only:

- period: `2026-06-16T00:00:00+00:00` through
  `2026-07-16T00:00:00+00:00`;
- timeframe: `1h`;
- tick types: `mark`, `spot`;
- bounded to one page per series and 1,000 candles per request;
- `2,884` closed candle rows and `1,442` aligned same-quote basis rows were
  written without collection errors;
- the accumulated basis history contains `3,976` valid same-quote rows and
  satisfies the collector's research-data coverage threshold;
- historical funding remains available from `2025-07-02` through
  `2026-07-15`.

The capability scanner now reports `funding_basis` as
`DATA_AVAILABLE_RESEARCH_ONLY`.  This means its input data exists; it is not
evidence of alpha and does not make any strategy eligible for shadow, paper or
live trading.

## Verification

- targeted collector/scanner/feature/CLI suite: `70 passed`;
- complete local suite: `1565 passed, 5 skipped`;
- local compilation: passed;
- `git diff --check`: passed;
- VPS commit: `1e9c03ba041e80d13300149e83f810aaa494ad85`;
- VPS container and `/health`: healthy; WebSocket connected; 14 instances.

## Safety Evidence

- collection used public market-data endpoints only;
- the smoke collector ran in an isolated disposable container and did not
  mount the runtime state database;
- no private Kraken endpoint or order path was called;
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`;
- `LIVE_TRADING_CONFIRMATION=false`;
- `STRATEGY_ROUTER_LIVE_ENABLED=false`;
- `COLONY_AUTO_LIVE_PROMOTION=false`;
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`;
- grid remains retired/no-go.

## Residual Risks and Next Gate

- The basis history is only thirty days; it is enough to validate the data
  pipeline, not to claim a durable relationship or fit parameters.
- Open-interest history is still forward-collected and remains unavailable as
  a historical feature.
- The canonical spot OHLCV window is still about one month; a longer bounded
  history is required for robust walk-forward validation.
- A funding/basis hypothesis must next enter the existing experiment registry
  and pass data checks, net-cost smoke, out-of-sample, statistical and shadow
  gates.  It remains research-only until all of those gates pass.
