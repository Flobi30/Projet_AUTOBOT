# AUTOBOT Block 2 — Registry-Bound Statistical Validation — 2026-07-29

## Scope

This local change hardens research-only multiple-testing evidence.  It does
not run a strategy, collect data, start shadow runtime, enable paper capital,
promote an artifact, change sizing or leverage, call a private endpoint, or
submit an order.

## Change

- Added the immutable `StatisticalValidationArtifact` contract to the
  append-only experiment registry.
- A passed `STRESS_MONTE_CARLO` transition now requires the artifact alongside
  the existing PSR, DSR and robustness evidence.
- The artifact binds the experiment, campaign/hypothesis trial scope,
  registry trial floor, effective trial count and deterministic fingerprint.
- The effective count may be more conservative than the registry floor, but
  cannot understate it.
- `record_runner_evidence()` builds and attaches the artifact after recording
  its bounded candidate plan; a caller-supplied scope is replaced by the
  registry-owned scope.
- The registry re-computes the evidence before persisting the passed stress
  transition, rejecting tampered counts, scopes, experiments or fingerprints.

## Tests

Local commands:

```text
python -m compileall -q src
PYTHONPATH=src python -m pytest \
  tests/research/test_experiment_registry.py \
  tests/research/test_shadow_governance.py \
  tests/research/test_strategy_artifact_cli.py \
  tests/research/test_statistical_validation.py \
  tests/research/test_funding_basis_statistical_validation.py \
  tests/research/test_volatility_reversal_statistical_validation.py \
  tests/research/test_alpha_hypothesis_runner.py \
  tests/test_v2_cli.py -q
```

Result:

```text
121 passed
```

The tests cover a lower attempted count, a mismatched count, a valid
append-only artifact and automatic attachment by the generic runner path.

Full local non-regression executed after the targeted suite:

```text
PYTHONPATH=src python -m pytest -q
2044 passed, 6 skipped, 2 deselected in 58.53s
```

## Decision

`GO_LOCAL` — Block 2 has a stronger generic boundary between trial planning
and statistical evidence.  It remains `PARTIAL`: a future adapter still has
to use the shared runner/registry path to obtain this protection.

## Deployment

The Hetzner VPS is unavailable because of the reported account-maintenance
outage.  No VPS deployment or runtime check was attempted.  A controlled
rebuild and smoke verification remain required after service restoration.
