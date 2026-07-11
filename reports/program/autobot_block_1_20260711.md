# AUTOBOT Block 1 - Point-in-time data and feature registry

**Decision: GO for the next research block.** This delivery remains strictly
research-only. It does not enable paper capital, live trading, automatic
promotion, sizing, leverage, or an order runtime path.

## Delivered

- Canonical OHLCV schema v2 keeps the legacy open timestamp unchanged and adds
  `event_time`, `available_time`, `ingestion_time`, `bar_close_time`, source
  timestamp role, availability basis, explicit market mapping status, and a
  versioned migration adapter.
- A completed OHLCV bar becomes available only at/after its close. Naive or
  conflicting legacy timestamps are quarantined rather than interpreted.
- The Kraken Futures public collector records temporal/provenance fields,
  separates economic from provenance fingerprints, rejects unclosed candles,
  keeps basis same-quote only, and does not discard valid mark/index data just
  because open interest is malformed.
- `FeatureDefinition` and `FeatureRegistry` provide deterministic research
  features for returns, momentum, volatility, ATR, spread, funding, basis, and
  open-interest change. Feature values carry a definition fingerprint and an
  explicit `READY`, `DATA_MISSING`, or `WAITING_FOR_MORE_DATA` status.
- Historical and shadow replay both use the same registry evaluator. The
  parity harness proves that input order cannot alter output features.
- Regime segmentation is bounded and logged as a research trial; price history
  is now kept independently per symbol and timeframe.

## Evidence

- Focused data / feature / contract / safety regression: `101 passed`.
- Full research suite: `285 passed`.
- Compilation and whitespace validation passed.
- The Windows checkout needs a short worktree path for historic report files
  with deep names. The Linux VPS does not have this path-length limitation and
  remains the deployment validation environment.

## Remaining boundaries

- Historical funding is honestly marked available at its backfill ingestion
  time until a point-in-time source availability contract is available.
- Basis and open-interest history remain insufficient until multiple real
  snapshots accumulate; the collector does not mark a few snapshots as ready.
- The registry is research-only. Strategy and shadow callers are not switched
  to it until Block 4 parity/gating work, avoiding a runtime behavior change in
  this data-foundation block.

## Deployment evidence

- Commit: this versioned report is committed with the Block 1 delivery; its
  revision is the authoritative release identifier.
- GitHub / VPS / container validation is recorded with the deployment smoke
  after this immutable source package has passed isolated verification.
- Safety expectation after deployment: paper capital off, live confirmation
  false, strategy router live false, automatic promotion false, Grid retired.
