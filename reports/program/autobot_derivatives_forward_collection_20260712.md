# AUTOBOT — Derivatives Forward Collection, 2026-07-12

## Decision

**GO — research-only forward collection enabled.**

The new job builds a public Kraken Futures archive for funding context, mark/index basis, predicted funding and open interest. It cannot call an order endpoint and does not enable shadow trading, paper capital, promotion, leverage, sizing or live trading.

## What changed

- Per-run derivatives CSVs remain immutable audit records.
- Ticker and basis observations are compacted atomically into deduplicated canonical histories.
- Compact history is keyed by exchange, futures symbol and event timestamp, so retries cannot inflate the effective dataset.
- Existing historical funding and derivative candles are compacted once and retained when a later ticker-only run skips their expensive backfill.
- Readiness requires every mapped instrument to have at least 96 observations spanning seven days. A current snapshot is never treated as historical basis or open-interest evidence.
- The capability scanner now reports the compact historical sources and row counts.
- A separate systemd timer runs every 15 minutes in an isolated, read-only container with only `data/` mounted.

## VPS smoke evidence

- GitHub, VPS and running container commit: `5a58dbf05db58352395a82ef203129e0ea267b0d`.
- `autobot-v2` health: healthy; orchestrator running; WebSocket connected; 14 instances.
- Derivatives service result: success.
- Public mappings collected: BTC, ETH, SOL, XRP, ADA and LINK perpetuals.
- Funding history compacted: 53,668 rows from 2025-07-02 through 2026-07-10.
- Basis/open-interest forward history: 20 rows at smoke completion; still below the seven-day/96-observation policy.
- `funding_basis`: `WAITING_FOR_MORE_DATA`.
- `liquidation_cascade`: `DATA_MISSING`.

## Validation

- Targeted collector, scanner and deployment tests: 19 passed.
- Full research suite: 341 passed.
- Python compilation and diff whitespace checks: passed.
- Systemd unit syntax verified before installation.

## Safety invariants verified

- `LIVE_TRADING_CONFIRMATION=false`.
- Paper execution adapter, strategy-router live mode, auto-promotion and dynamic paper rebalancing remain disabled.
- The collector uses only Kraken Futures public ticker and instrument endpoints every 15 minutes; funding/candle backfills are skipped by the periodic job.
- No API key, `.env`, private endpoint, router, executor or order path is mounted into the collection container.
- Grid remains retired/no-go.

## Residual risk and next gate

Forward basis and open-interest history must accumulate before `funding_basis` can even enter research validation. Historical funding alone is not an alpha and has not unlocked paper or live behavior.

The next implementation task remains feature parity and experiment provenance: bind any later derivative feature to its canonical history fingerprint, point-in-time availability and experiment manifest before a research hypothesis can consume it.
