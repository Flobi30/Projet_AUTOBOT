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
- Isolated VPS image at commit `8b90047e0bf6e3e217ece4169134473b97e08bcd`:
  `432 passed` across research, shadow-observation and CLI coverage, with no
  network and no Linux capabilities.
- VPS source and rebuilt `autobot-v2` container are aligned on that commit.
- `/health` reports the orchestrator running, WebSocket connected and 14
  instances. Paper execution adapter, live confirmation, router live and
  auto-promotion flags are all false.
- No critical or live-order log was found immediately after restart.

## Decision

`GO_INCREMENT`. The anti-overfitting accounting increment is deployed; Block 2
remains in progress until its remaining generic validation and holdout-review
work are audited and integrated.
