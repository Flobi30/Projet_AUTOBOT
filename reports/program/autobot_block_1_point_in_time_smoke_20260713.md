# AUTOBOT Block 1 — Current-Run Point-in-Time Smoke

## Decision

**GO for continued research collection; no strategy gate changes.**

The scheduled daily collection that ran before the latest runtime image still
used the older CSV schema. A bounded public-data smoke was therefore run after
deployment using the current image, separate from the trading runtime.

## Evidence

- Public Kraken spot BTC/EUR, 5-minute OHLCV only.
- 720 closed bars collected; the incomplete current bar was excluded.
- All rows carry explicit `available_time` and `ingestion_time`.
- Canonical snapshot: `ohlcv_v2_b5ea4b9f47983e27`.
- Explicit Kraken market mapping used; no USD/EUR conversion or inferred
  symbol mapping.
- Canonical rows: 720; duplicates: 0; gaps: 0; quarantined rows: 0.
- Feature snapshot: `features_v1_c4c5d83998ea5f3f`.
- Feature parity: true; unknown ingestion timestamps: 0; ready feature values:
  2,842; warm-up values remain explicitly waiting.

## Safety

- Containers were read-only apart from the research data mount.
- Only public Kraken endpoints were used; no key, secret, private endpoint or
  order endpoint was available to the smoke jobs.
- No shadow activation, paper capital, promotion, leverage, sizing or live
  setting changed.

## Interpretation

This confirms the point-in-time data and feature path works with current-run
data. It is not evidence of an alpha: the sample covers about 2.5 days on one
asset and has no bid/ask or depth history. The collector must continue to
accumulate current-run snapshots before an experiment can use them as a valid
runtime-parity dataset.

## Next gate

The next systemd collection is scheduled for 2026-07-14 00:19 UTC and will use
the newly deployed image. It must produce a daily canonical manifest and a
feature manifest from its own raw paths; otherwise Block 1 remains blocked for
repair.
