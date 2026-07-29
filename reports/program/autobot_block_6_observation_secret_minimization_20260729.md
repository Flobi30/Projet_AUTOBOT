# AUTOBOT Block 6 — Observation Runtime Secret Minimization

## Finding

The observation-only application did not construct a private executor, but it
still retained and forwarded private exchange credentials from its environment.
The async executor representation also exposed a short key prefix.

## Change

- In observation-only mode, `AutoBotV2Async` discards supplied and environment
  exchange credentials before it can construct the orchestrator, and removes
  the two legacy exchange credential variables from its own process
  environment.
- `OrderExecutorAsync.__repr__` now reports only whether credentials are
  configured; it never includes key material.

## Safety Result

This change does not alter public-data collection, order routing, paper
capital, live trading, promotion, sizing, leverage or runtime flags. It
reduces secret propagation inside the active observation-only process.

## Deployment

Hetzner maintenance is active. No VPS validation or service action is
attempted until access resumes.
