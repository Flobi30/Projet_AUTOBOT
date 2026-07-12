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
- Batch CLI reports default to `data/research/reports/`, which is writable by
  the locked-down container. Versioned project reports stay separate under
  `reports/program/`.
- Monotonic canonical series use only the maximum declared feature lookback;
  delayed or out-of-order input retains the stricter general point-in-time
  filter. This keeps a full historical materialization bounded without
  weakening temporal checks.

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

## VPS evidence

Validated on the VPS at code commit `e0852cf7f268385dcf4ec57f017a22dce6b1f62e`.

- Canonical rebuild: `883,225` raw rows, `176,918` canonical rows, `706,307`
  deterministic duplicates removed, `0` gaps and `0` quarantined rows.
- Canonical snapshot: `ohlcv_v2_0ab59816b52c77c6`, covering 14 EUR spot
  markets and 5m/15m/1h timeframes. Public Kraken metadata supplied 36
  explicit market mappings.
- Feature snapshot: `features_v1_efb1946a8298900e`, with `707,672` feature
  values, `706,076` ready values, `1,596` expected warm-up values, `0` missing
  values and deterministic parity confirmed.
- Unknown source ingestion time remains an explicit blocker on all migrated
  legacy rows. This bundle is valid research evidence, not proof of full
  runtime point-in-time parity.
- Storage used: approximately 69 MB canonical OHLCV and 209 MB features;
  the VPS retained about 63 GB free before the feature materialization.
- Local verification: 330 research tests and 67 targeted safety/integration
  tests passed; source compilation and diff checks passed.
- VPS: container healthy, WebSocket connected, 14 instances. All paper bridge,
  legacy direct-entry, capital-reallocation, leverage, instance-split and live
  promotion flags were false. No traceback, critical or live activity appeared
  in the post-deployment logs.

## Updated decision

`GO` for the next research-only stage: use the versioned feature snapshot in
the Alpha Lab and experiment registry. `REWORK` is still required before any
claim of runtime/shadow parity because the historical source did not preserve
its ingestion time. No promotion, paper capital or live activation is allowed.
