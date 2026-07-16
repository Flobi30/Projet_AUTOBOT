# AUTOBOT Block 1 — Derivatives Capability Wiring (2026-07-16)

## Verdict

`GO_LOCAL` — deploy the scheduler capability-path separation, then validate the
next scheduled report on the VPS. This change does not unlock or run a
derivatives strategy.

## Finding

The VPS already has the public Kraken Futures research collector enabled:

- the ticker and funding refresh timers are enabled and active;
- the audit found 375 derivatives manifests and 1,508 canonical derivatives
  files;
- the latest ticker manifest had verified same-quote current basis and current
  open interest, but basis history and open-interest history remain incomplete.

The daily scheduler and bounded coordinator previously received only the
canonical OHLCV directory. They therefore could not see the existing
derivatives manifest and reported derivatives as generically missing.

## Change

`AlphaSchedulerConfig` now separates two read-only inputs:

- `data_paths`: market data available to a runner;
- `capability_data_paths`: manifests and canonical roots used only to assess
  what data capabilities exist.

The daily scheduler and the bounded coordinator retain
`data/research/canonical/ohlcv` as their only runner market-data input. They
now scan `data/research/canonical/ohlcv,data/research/manifests` for readiness.
This lets the scheduler report `WAITING_FOR_MORE_DATA` for funding/basis when
appropriate, without letting an OHLCV runner ingest derivatives CSVs.

## Safety

- No strategy, order, paper-capital, live, promotion, sizing, leverage or UI
  path changed.
- The derivatives collector stays public-market-data research only.
- `funding_basis` remains blocked until its historical basis gate is genuinely
  satisfied.
- The bounded coordinator allowlist remains unchanged and cannot autonomously
  run a funding/basis experiment.

## Local validation

- Targeted scheduler/coordinator/service suite: `25 passed`.
- Full suite: `1542 passed, 5 skipped`.
- Python syntax compilation: passed for touched modules.
- `git diff --check`: passed.

## Residual risk and next gate

Current basis history is still too short and current open interest is not an
open-interest history. The correct next outcome is continued public research
collection and an explicit `WAITING_FOR_MORE_DATA` status; it is not a strategy
promotion or a paper-capital activation.
