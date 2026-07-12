# AUTOBOT — Point-in-Time Feature Pipeline — 2026-07-12

## Scope

This increment closes a real data-boundary gap before any strategy is allowed
to rely on canonical features. It remains batch-only and research-only.

## Delivered

- Kraken public `AssetPairs` metadata now provides an explicit base/quote
  mapping for supported markets. Unknown venue identifiers remain unverified;
  no compact-symbol parsing is used to invent a quote currency.
- `canonicalize-ohlcv` now uses those public mappings by default and records
  the number of explicit mappings used. `--market-mapping-source none` remains
  available only for an intentionally unverified migration.
- `materialize-feature-snapshot` creates deterministic feature bundles from a
  canonical OHLCV v2 manifest using the shared `FeatureRegistry`.
- The feature bundle records its source snapshot, source fingerprint, feature
  registry fingerprint, explicit-mapping exclusions and feature parity result.
- Unknown source ingestion time remains visible as
  `INGESTION_TIME_UNKNOWN_RUNTIME_PARITY_NOT_PROVEN`; it is never fabricated.

## Safety invariants

- No runtime, router, paper engine, execution adapter or private Kraken API is
  imported by the batch feature materializer.
- No shadow activation, paper capital, promotion, live trading, sizing or
  leverage change is introduced.
- Rows with `MAPPING_UNVERIFIED` are excluded from feature materialization.

## Remaining gate

The existing VPS canonical data is legacy schema v1 and cannot be used as
feature-gate evidence. It must be rebuilt from the preserved raw OHLCV inputs
with public Kraken mappings, then materialized with the new feature command.
Its source ingestion time will still be marked unknown until a collector
records it at ingestion; that prevents any false claim of full runtime parity.

## Decision

`GO` for a bounded VPS rebuild and feature-materialization smoke. The result
is expected to remain research-only and non-promotable.
