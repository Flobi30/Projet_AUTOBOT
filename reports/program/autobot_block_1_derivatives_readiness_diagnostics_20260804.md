# Block 1 - Derivatives readiness diagnostics

## Decision

`GO_VPS_VALIDATION_PENDING`

## Scope

The research-only funding/basis availability contract now exposes the actual
per-futures observation counts used by its existing data gate, together with
the configured thresholds. This explains why a technically `READY` derivative
feature snapshot can still be `WAITING_FOR_MORE_DATA` for a strategy adapter.

## Changes

- Added funding and basis observation counts keyed by the explicit futures
  symbol to `FundingBasisAvailability`.
- Added the configured minimum funding-observation and signal-eligible-bar
  thresholds to the same read-only availability report.
- Preserved the explicit futures-to-spot map so diagnostics cannot imply a
  USD/EUR price conversion.
- Added a boundary test covering short forward history and the reported
  thresholds.

## Evidence

- Funding/basis adapter, walk-forward and runner tests: `26 passed`.
- Python compilation passed for the changed adapter.
- `git diff --check` passed.

The latest inspected forward derivative feature snapshot has 26 funding
observations per mapped BTC/ETH future, while the adapter requires 30. The
correct status remains `WAITING_FOR_MORE_DATA`; no threshold was relaxed and
no alpha run was started.

## Safety

- Read-only availability metadata only.
- No collection, NET_SMOKE, shadow, paper capital, live, promotion, sizing,
  leverage, order endpoint or dashboard change.
- Grid remains outside the runtime path.

## Remaining validation

Deploy the diagnostics-only change, then let the scheduled public-data cycle
accumulate forward history. A future human-guided `DATA_CHECK` remains gated
on the adapter's reported counts and overlap, not on snapshot status alone.
