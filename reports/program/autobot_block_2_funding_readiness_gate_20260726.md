# AUTOBOT — Funding/Basis readiness gate — 2026-07-26

## Decision

`REWORK_COMPLETE`: the funding/basis `DATA_CHECK` now uses the same
point-in-time availability check as the bounded research adapter.  A forward
feature manifest can be structurally valid while still being too short for a
strategy experiment; that condition is now reported as
`INSUFFICIENT_DATA` before `NET_SMOKE` is entered.

## Evidence that prompted the change

The isolated P20 research run used only the canonical spot snapshot and the
forward-captured derivatives snapshot.  Its manifest integrity, same-quote
basis contract and research/shadow parity were valid.  The adapter nevertheless
found only 262 relevant BTC/ETH derivative observations and returned:

```text
derivatives_history_insufficient:BTCZEUR
derivatives_history_insufficient:ETHZEUR
```

It created no simulated trade and made no paper, live, promotion or runtime
change.  The experiment registry records the resulting `NET_SMOKE` state as
`INSUFFICIENT_DATA`.

## Change

- `build_funding_basis_availability()` is a no-signal, no-trade helper shared
  by the adapter and the runner.
- The runner calls it during `DATA_CHECK` after manifest validation.
- Short derivative history now stops at `DATA_CHECK` with
  `funding_basis_adapter_waiting_for_more_data`; it cannot consume a smoke
  gate or be misreported as runnable.
- The helper only reads canonical research inputs.  It imports no order,
  paper, live or private-exchange component.

## Test foundation repair

The full local suite initially exposed a separate baseline issue: invoking
`python tools/paper_ops.py` directly could not import the repository `src/`
layout.  The operator tool now adds that local source root before importing
AUTOBOT modules.  This changes neither trading behaviour nor configuration;
it makes the existing CLI integration tests represent the documented command.

## Validation

- focused funding/basis, manifested-experiment, shadow-boundary and operator
  CLI suites: `97 passed`;
- complete local suite: `1895 passed, 6 skipped, 2 deselected`;
- Python compilation and `git diff --check`: passed;
- no secret value was introduced.

## Current operating rule

Funding/basis collection continues through the isolated research timers.  No
new funding/basis experiment is run until a later snapshot materially changes
the available history and the shared availability gate reports `READY`.

## Safety invariants

- research-only, network-disabled runner container;
- no runtime state DB, secrets, `.env` or order surface mounted;
- `PAPER_TRADING=false` and all paper/live/promotion flags remain false;
- grid remains retired/no-go;
- a positive result would still require walk-forward, statistical validation
  and human review before any risk increase.
