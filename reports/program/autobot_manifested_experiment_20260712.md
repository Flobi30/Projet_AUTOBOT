# AUTOBOT — Manifested Experiment Registry — 2026-07-12

## Scope

This increment binds a research run to a verified feature-snapshot manifest and
appends its evidence to the experiment registry. It is research-only and has
no runtime execution dependency.

## Delivered

- `alpha-hypothesis-runner` can now receive a verified feature manifest and
  append the run to `ExperimentRegistry`.
- The recorded material identity includes source snapshot and fingerprint,
  feature snapshot and fingerprint, feature registry fingerprint, explicit
  feature versions, cost profile, code commit, parameters and seed.
- A feature manifest lacking a verified registry fingerprint or deterministic
  parity is rejected before an experiment can be registered.
- Older manifests can be upgraded into a separate file only when their stored
  registry fingerprint exactly matches the active registry. The feature bundle
  itself is never recomputed or overwritten by that migration.
- Gate mode/run ID no longer changes a material experiment fingerprint. The
  same hypothesis can advance through its allowed gates rather than create a
  fresh experiment per command.

## VPS evidence

At commit `d0dc2017b6b324591ae8a549b12ca062ac87028b`, the upgraded feature
manifest was registered for a bounded `long_trend` run using canonical snapshot
`ohlcv_v2_0ab59816b52c77c6` and feature snapshot
`features_v1_efb1946a8298900e`.

- The data gate passed for 75,822 selected rows across six EUR spot symbols.
- The net smoke then rejected the material experiment:
  - 429 trades;
  - net PnL: -309.30 EUR;
  - PF net: 0.590;
  - expectancy net: -0.721 EUR;
  - max drawdown: 311.00 EUR.
- The experiment is terminal `REJECTED` at `NET_SMOKE`; no walk-forward,
  shadow, paper capital or live transition is permitted for this fingerprint.
- The registry entry remains research-only and has all paper/live/promotion
  permissions set to false.

## Interpretation

This is not a failed deployment. It is a successful research gate: a known
weak trend configuration was rejected using a reproducible canonical dataset
instead of being parameter-tuned toward a misleading result.

## Next decision

`GO` for other bounded hypotheses whose required data is present. Funding/basis
remains research-only and must stay blocked until its basis history has enough
coverage. No capital path may use the rejected `long_trend` experiment.
