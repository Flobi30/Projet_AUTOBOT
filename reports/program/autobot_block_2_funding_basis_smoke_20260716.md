# AUTOBOT Block 2 — manifested funding/basis smoke — 2026-07-16

## Decision

`STOP / INSUFFICIENT_DATA` for this exact material experiment.  The runner
created no executable trades, so it did not advance to walk-forward, stress,
shadow, paper capital, or live.  This is a valid research outcome, not a
signal to relax a gate or retry the same material experiment.

## Scope

- Code commit: `ab6902a1798dbb151eb5fd77d3c6f41e9743e327`.
- Hypothesis: `funding_basis`.
- Template: `funding_extreme_reversion`.
- Mode: bounded `smoke`, research-only, one variant, two symbols, one
  explicitly counted timeframe (`1h`).
- Symbols: `BTCZEUR`, `ETHZEUR`.
- Cost profile: `research_stress`.
- Spot snapshot: `features_v1_fd934cf37210b7c2`, deterministic parity proven.
- Derivatives snapshot: `derivatives_features_v1_719365bf7cd63b9b`, with
  same-quote basis validation and funding data.

## Evidence

The data gate passed: the manifest contains the required `basis_bps` and
`funding_rate_relative` features, has a verified same-quote basis contract,
and rejects an implicit USD/EUR conversion.

The net-cost smoke produced zero executable trades for the bounded 5th
percentile funding / 24-hour hold variant.  Consequently gross PnL, net PnL,
fees, slippage, profit factor, expectancy and drawdown are not estimable for
this experiment.  The official no-trade baseline remains zero.

The append-only experiment registry recorded:

- experiment: `exp_59aca86b1d287e7164e3`;
- material fingerprint: `59aca86b1d287e7164e332d30cf5b029f0ab1bc575cf8f7095d7149b148214e4`;
- terminal status: `INSUFFICIENT_DATA` at `NET_SMOKE`;
- accounted trial count: `6`.

The runtime-generated evidence remains on the VPS data volume:

- `data/research/reports/alpha_runner/block2_funding_basis_smoke_20260716.json`;
- `data/research/reports/alpha_runner/block2_funding_basis_smoke_20260716.md`;
- `data/research/experiment_registry.sqlite3`.

## Boundaries and blockers

- The derivatives snapshot has 16 historical rows with unknown ingestion time.
  It remains valid for offline research but cannot prove derivatives runtime
  parity.  It cannot support shadow or any capital decision.
- The current canonical spot window is approximately 30 days.  It is not a
  sufficient independent holdout for optimisation or promotion.
- The exact material experiment is terminal.  A future run needs materially
  different data coverage, a distinct pre-registered thesis/template, or both.

## Safety confirmation

- No runtime order path was imported or called.
- No paper capital, live activation, promotion, sizing, leverage or UI change
  occurred.
- Grid remains retired/no-go.

## Next action

Continue passive, bounded derivatives collection and improve point-in-time
coverage.  Do not automatically retry this experiment.  The next research
proposal must be independently specified and pass the same manifest, cost and
trial-accounting gates before it can run.
