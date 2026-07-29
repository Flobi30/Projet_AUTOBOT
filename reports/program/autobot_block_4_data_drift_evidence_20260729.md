# AUTOBOT Block 4 — Data Drift Evidence Binding (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the shadow-safety policy now treats data-distribution drift
as structured research-only evidence, not as a caller-supplied scalar.

## Finding

`ShadowPerformanceWindow` previously required provenance-bearing
`FeatureDriftAssessment` evidence for feature drift, but accepted a bare
`data_drift_score`. This permitted a data-drift score to be supplied without
the distribution evidence used to calculate it. Conversely, an absent data
drift measure was not reported as an observation risk.

## Change

- `DataDriftAssessment` now validates positive finite population mass,
  category identity, bounded total-variation score and research-only flags.
- `ShadowPerformanceWindow` accepts `DataDriftAssessment` evidence and derives
  `data_drift_score` from it. A supplied score must match the evidence exactly.
- A score without evidence is rejected; no evidence produces an audited
  `WATCH` decision (`data_drift_evidence_missing`).
- Verified data-drift evidence continues to only reduce the shadow envelope;
  it has no paper, live or promotion authority.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_shadow_governance.py \
  tests/research/test_experiment_registry.py \
  tests/research/test_strategy_artifact_cli.py \
  tests/research/test_shadow_review_evidence.py \
  tests/research/test_feature_registry.py -q
```

Result: `72 passed`.

The regression coverage includes missing, injected, mismatched and derived
data-drift evidence, plus existing artifact, experiment, feature and shadow
review boundaries.

## Safety

- No runtime order, paper-capital, live, promotion, sizing or leverage path
  changed.
- Grid remains retired/no-go.
- No SSH, VPS, Docker, database or runtime flag operation was attempted while
  the VPS is unavailable.

## Residual Risk

The evidence contract binds an assessed distribution to a decision but does
not yet carry dataset/snapshot lineage comparable to the feature-vector
contract. That stronger provenance belongs to the Block 1/4 data feature
materialisation work and remains `PARTIAL` until runtime collection resumes.
