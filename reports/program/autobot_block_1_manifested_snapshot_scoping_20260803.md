# AUTOBOT Block 1 — Manifested snapshot input scoping

## Decision

`GO_WITH_WAITING_FOR_DATA` for the data-provenance correction.  The
`funding_basis` hypothesis remains blocked at `DATA_CHECK`; no smoke, shadow,
paper-capital or live action is authorised by this change.

## Problem found

The research runner accepted `data/research/canonical/ohlcv` as an input even
when its feature manifest named one immutable source snapshot.  That root
contains historical snapshots with overlapping OHLCV bars, so the adapter
correctly reported duplicate bars but could not distinguish a data-quality
failure from an invalid multi-snapshot query.

## Change

- A feature manifest now narrows a canonical root to its exact
  `source_snapshot_id` child.
- An already-scoped snapshot directory or file remains valid.
- Any path that cannot resolve to the manifested snapshot fails closed before
  an experiment is registered or a runner calculates metrics.
- The bounded research coordinator uses the same resolved paths as its
  manifested experiment evidence and its research-only runner.

This keeps feature provenance, input bars and experiment fingerprints aligned.

## VPS data-check evidence

- Time: `2026-08-03T16:22Z`.
- Scope: one network-isolated, read-only-root `funding_basis` `DATA_CHECK` for
  `BTCZEUR,ETHZEUR`; no order, paper-capital, live or promotion path was
  available.
- Outcome before this correction: `INSUFFICIENT_DATA`.
- Genuine remaining blockers: forward derivatives history is below the
  adapter minimum for both `BTCZEUR` and `ETHZEUR`.
- The duplicate-bar blocker came from mixing historical canonical snapshots
  under the broad root and is addressed by this change.

## Tests

```text
python -m pytest \
  tests/research/test_funding_basis_research_adapter.py \
  tests/research/test_derivatives_feature_snapshot.py \
  tests/research/test_alpha_hypothesis_runner.py \
  tests/research/test_manifested_experiment.py \
  tests/research/test_bounded_research_coordinator.py \
  tests/test_v2_cli.py -q
# 102 passed

python -m compileall -q src
git diff --check
```

## Safety invariants

- Research-only behavior remains enforced.
- Grid remains retired/no-go.
- `paper_capital_allowed`, `live_allowed` and `promotable` remain false.
- The next permitted action is a new human-guided `DATA_CHECK` using an exact
  spot snapshot after derivative history grows; `NET_SMOKE` remains forbidden
  until that gate passes.
