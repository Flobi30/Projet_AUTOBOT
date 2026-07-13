# AUTOBOT - Block 2 Trial Accounting - 2026-07-13

## Scope

This increment strengthens research reproducibility and multiple-testing
control. It remains isolated from strategy runtime, paper execution and live
execution.

## Delivered

- Material experiment plans are registered before the runner starts when a
  verified feature manifest and an explicit code commit are supplied.
- The registry records parameter variants, pairs, explicitly declared
  timeframes and explicitly declared regimes. It also records deterministic
  candidate configurations for validation statistics.
- The runner receives only a conservative trial-count floor; it does not
  access SQLite directly. The DSR/PSR path uses the greater of that floor and
  its local variant/pair/fold lower bound.
- Re-running a terminal material fingerprint is blocked before research work
  begins. A new data snapshot, thesis or template is required.
- A CLI command can reserve immutable holdout data. The reservation has no
  optimization, paper-capital, promotion or live capability.

## Safety invariants

- No strategy is added or promoted.
- No paper capital, live flag, sizing, leverage, router or order path changes.
- Grid remains outside the official runtime path.
- Omitted timeframe and regime values remain `UNSPECIFIED`; the system does
  not invent research dimensions from a report.

## Validation

- Focused registry, manifested-experiment, runner and CLI tests: `57 passed`.
- Touched Python modules compile successfully.
- Full isolated container validation and VPS smoke remain required before this
  increment is accepted as deployed.

## Decision

`GO_LOCAL_ONLY` pending the currently running research collection finishing,
then isolated-image validation, controlled deployment and VPS smoke checks.
