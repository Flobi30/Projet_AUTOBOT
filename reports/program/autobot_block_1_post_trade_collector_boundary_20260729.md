# AUTOBOT Block 1 - PostTrade public collector boundary - 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`

The bounded Kraken Spot PostTrade backfill is now included in the canonical
public-collector inventory and fail-closed preflight.

## Change

- The PostTrade collector is listed in `PUBLIC_COLLECTOR_MODULES`.
- The direct public `AssetPairs` symbol-mapping fetcher is listed and audited
  before it may open its public HTTP request.
- Its collection entrypoint runs the static public-collector audit before it
  constructs a default HTTP client or invokes a caller-provided client.
- The test suite proves a synthetic audit failure aborts PostTrade collection
  before any input/output or public network activity.
- A static test keeps every current `urlopen`-based research source registered
  in the boundary inventory.

## Safety

- Public Kraken market data only; no credentials or private API are used.
- No paper capital, live, promotion, sizing, leverage or order path changed.
- Historical PostTrade bars remain research-only and retain their explicit
  `HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION` temporal status.

## Local proof

- `python -m compileall -q src`: passed.
- Public-collector, PostTrade, daily-collection and CLI suites: `71 passed`.
- No collector command was run against Kraken during validation.

## VPS follow-up

After Hetzner is restored, deploy this commit with the normal controlled
workflow. No data collection is required for the deployment smoke; the
collector may only be run later as a separately bounded public-data job.
