# AUTOBOT Blocks 1–2 — Derivatives History and Funding/Basis Gate — 2026-07-17

## Decision

`REWORK / STOP` for the exact manifested `funding_basis` experiment.

The data pipeline is now capable of producing a same-quote, public-market-data
research input.  The tested hypothesis is nevertheless terminally rejected at
the net-cost smoke gate.  It does not advance to walk-forward, statistical
validation, shadow, paper capital or live trading.

## Delivered Evidence

- Code commit `e38cd008b2ec0551bb5492b89f3fc6195583f3ea` fixes the capability
  scanner so it reports canonical basis-history coverage rather than only the
  newest collection batch.
- The focused scanner, scheduler, collector and derivatives-feature suite
  passed: `57 passed` (two environment-only pytest configuration warnings).
- The VPS source and AUTOBOT container were rebuilt on that commit; `/health`
  reported healthy, the WebSocket connected and 14 instances running.
- A read-only capability scan on the VPS reports:
  - same-quote basis: 55,682 canonical rows, from `2025-07-17` to
    `2026-07-17`;
  - open interest: 52,638 canonical rows over the same approximate period;
  - `funding_basis`: `DATA_AVAILABLE_RESEARCH_ONLY`.
- A derivatives point-in-time snapshot was materialized at
  `2026-07-17T12:00:00+00:00` with 58,230 feature values.  It accepts only
  verified same-quote basis sources and explicitly forbids implicit USD/EUR
  price conversion.

## Bounded Research Experiment

- hypothesis: `funding_basis`;
- template: `funding_extreme_reversion`;
- scope: four mapped EUR spot symbols, `1h`, two predeclared variants and the
  `research_stress` cost profile;
- experiment: `exp_072efed8921d363c6019`;
- material fingerprint:
  `072efed8921d363c6019248351b7f9b803cb2c3b5aade5bd9cd14b63596e949f`;
- accounted trials: 15;
- output: `NET_SMOKE / REJECTED / terminal`.

The data check passed for offline research.  The bounded smoke then produced
one primary trade only, with gross PnL `-1.317206 EUR`, net PnL `-2.297206
EUR`, PF net `0.0` and a round-trip cost estimate of `98 bps`.  The alternative
predeclared variant was not selected by best-PnL hindsight.  The rejection is
therefore based on predeclared order, negative net edge, PF not above one,
negative expectancy and an insufficient sample.

## Important Boundaries

- No order endpoint, router, paper capital, live activation, promotion,
  sizing, leverage or UI path was called or changed.
- The collector, materializer, capability scan and runner used isolated
  disposable containers; the runner had no network and no runtime state DB.
- Spot returns were calculated from mapped EUR spot bars only.  Derivatives
  USD data supplied directional context and never underwent an implicit
  USD/EUR conversion.
- The latest canonical spot snapshot spans only `2026-06-17` through
  `2026-07-17`.  This is too short for robust funding/basis validation even
  though the derivatives history is longer.
- The derivatives snapshot still reports
  `DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN` because a small number of historic
  observations lack an ingestion timestamp.  This blocks any future shadow
  eligibility; it does not justify weakening the offline-research boundary.

## Required Next Work

1. Extend point-in-time-correct spot history using an officially documented,
   bounded public-data route or continue forward accumulation; do not retry
   this exact material experiment.
2. Separate historic-backfill evidence from forward-collected runtime parity
   evidence and remove unknown-ingestion observations from any future shadow
   candidate input.
3. Only after materially new spot coverage or a genuinely distinct,
   pre-registered thesis exists, create a new experiment fingerprint and run
   the same data, cost, holdout and anti-overfitting gates.

The official Kraken Spot OHLC endpoint documents that it returns at most 720
recent entries, so it cannot by itself provide the missing one-year spot
history: <https://docs.kraken.com/api-reference/market-data/get-ohlc-data>.
