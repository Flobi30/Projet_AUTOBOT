# AUTOBOT Block 4 — Verified Feature-Drift Evidence

## Decision

`GO_LOCAL_ONLY` — feature drift can now influence the shadow safety policy only
through a derived, versioned assessment of point-in-time verified feature
vectors. No paper capital, live flag, promotion, sizing/leverage rule, runtime
service or order path changed.

## Scope

`assess_verified_feature_drift` derives total-variation distance from fixed,
predeclared histogram bins. The assessment requires:

- material-verified `VerifiedFeatureVector` inputs;
- one market and timeframe;
- one feature id/version;
- one feature-registry fingerprint;
- values available no later than the stated assessment time;
- unique immutable vector fingerprints for baseline and shadow samples.

`ShadowPerformanceWindow` no longer accepts a standalone
`feature_drift_score`. A supplied score must match a `FeatureDriftAssessment`;
when feature-drift evidence is unavailable, the monotonic policy records
`WATCH` rather than treating the shadow path as stable.

## Safety invariants

- The assessment is research-only with paper/live flags permanently false.
- Fixed bins prevent adaptive post-hoc grouping of the shadow distribution.
- Registry/version/market/timeframe mismatches fail closed.
- Future-dated vectors or feature values fail closed.
- A drift result can only lead to `WATCH`, `REDUCE`,
  `DISABLE_NEW_ENTRIES` or `QUARANTINE`.
- No drift outcome can start shadow, create an order, increase risk, promote a
  strategy, enable paper capital or enable live trading.

## Local validation

```text
python -m compileall -q src
PASS

PYTHONPATH=src python -m pytest \
  tests/research/test_shadow_governance.py \
  tests/research/test_runtime_shadow_preview.py \
  tests/research/test_runtime_shadow_decision_bridge.py \
  tests/research/test_shadow_review_evidence.py \
  tests/research/test_verified_feature_vector.py \
  tests/research/test_canonical_feature_snapshot.py -q
59 passed

PYTHONPATH=src python -m pytest -q
2052 passed, 6 skipped, 2 deselected
```

The focused tests prove deterministic feature-drift calculation, threshold
binding, rejection of an injected/mismatched score, fail-closed WATCH on
missing evidence, and rejection of a mismatched feature registry.

## Deployment state

The Hetzner VPS remains unavailable. This increment made no SSH attempt, no
deployment, no Docker action, no runtime or database write and no data
collection. VPS smoke verification remains deferred until access is restored.

## Remaining gate

Layer 19 remains `PARTIAL`. The evidence contract is local and hermetic; a
future read-only batch job may compute it from persisted canonical feature
snapshots, but that job must remain outside the runtime and must not activate
shadow, paper or live paths.
