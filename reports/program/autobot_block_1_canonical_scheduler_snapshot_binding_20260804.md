# Block 1 - Canonical scheduler snapshot binding

## Decision

`GO_LOCAL_VPS_VALIDATION_PENDING`

## Scope

The research scheduler now binds its readiness scan and any recommended runner
command to the exact immutable canonical OHLCV snapshot declared by a manifest.
It no longer treats the complete canonical archive as one dataset.

## Changes

- Added a manifest resolver that validates schema version, snapshot identity,
  market identity, file presence and snapshot containment.
- Added `--canonical-snapshot-manifest` to the report-only scheduler CLI.
- The daily research service passes the manifest created in the same collection
  run to its isolated scheduler container.
- Scheduler inputs fail closed if a manifest file falls outside `--data-paths`.
- The bounded coordinator claims its point-in-time snapshot before looking up a
  prior terminal experiment, so the duplicate-snapshot decision is stable.

## Evidence

- Focused boundary suite: `125 passed`.
- Complete research suite: `826 passed, 1 skipped`.
- Complete project suite: `2123 passed, 6 skipped, 2 deselected`.
- Python compilation passed for the changed modules.
- Shell syntax checks passed for the collection and rebuild scripts.
- `git diff --check` passed.

The latest VPS canonical manifest was inspected read-only before deployment. It
contains one snapshot with `30240` canonical rows and `0` duplicates; its CSV
paths are relative to the container research mount.

## Safety

- Research-only scheduler and coordinator paths only.
- No paper capital, live trading, promotion, sizing, leverage, order endpoint
  or dashboard change.
- Grid remains outside the runtime path.

## Remaining validation

Deploy the committed change, run only the isolated no-network scheduler against
the latest canonical manifest, and verify that its readiness scan reports the
manifest rows without archive-wide duplicate inflation. No data collection or
research smoke is required for this validation.
