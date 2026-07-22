# AUTOBOT - Research successor provenance and trial floors - 2026-07-22

## Decision

**GO - research-registry guard only.**

This increment makes a material-data successor explicit in the append-only
experiment registry. It neither registers a campaign nor schedules, runs,
promotes, shadows, papers or routes a strategy.

## Implemented boundary

- `ExperimentSpec` may bind a successor to its predecessor with:
  - `predecessor_experiment_id`;
  - `predecessor_trial_count_floor`;
  - `material_data_signature` containing a deterministic fingerprint and
    capability states.
- The registry accepts a successor only when the predecessor:
  - exists;
  - is terminal `INSUFFICIENT_DATA`;
  - has the same hypothesis and template;
  - has a comparable material-data signature;
  - has a signature different from the successor.
- A predecessor rejected for performance can never be relabelled as a
  data-refresh successor.
- The declared predecessor floor must cover the predecessor candidate-trial
  count. Campaign validation adds inherited floors, so a new campaign label
  cannot lower the multiple-testing burden.
- Legacy experiment material fingerprints remain unchanged when all newly
  optional fields are absent.

## Evidence and tests

Local checks before deployment:

```text
python -m compileall -q src
pytest tests/research/test_experiment_registry.py \
       tests/research/test_research_retry_eligibility.py -q
-> 29 passed

pytest tests/research/test_alpha_hypothesis_runner.py \
       tests/research/test_funding_basis_statistical_validation.py \
       tests/research/test_experiment_registry.py \
       tests/research/test_research_retry_eligibility.py \
       tests/test_v2_cli.py -q
-> 84 passed

pytest -q
-> 1862 passed, 6 skipped
```

The targeted tests cover a valid data-insufficiency successor, rejection of a
performance-rejected predecessor, rejection of unchanged material data and
rejection of a lowered inherited trial floor.

## VPS deployment validation

The implementation commit `c25eef3c04a4416453c9c8207f5bb3fb6ac21ee5` was
fast-forwarded to `/opt/Projet_AUTOBOT`, rebuilt through the approved deploy
script and recreated as `autobot-v2`.

```text
source HEAD: c25eef3c04a4416453c9c8207f5bb3fb6ac21ee5
container image revision: c25eef3c04a4416453c9c8207f5bb3fb6ac21ee5
/health: healthy; orchestrator running; WebSocket connected; 14 instances
runtime-generated/untracked VPS artifacts preserved: 13
isolated VPS pytest (network none, read-only source): 29 passed
```

All nine AUTOBOT research/resilience timers stopped only for the rebuild and
were restored afterwards.

## Safety confirmation

- Research registry only; no runtime, router, executor, paper or live import
  is added.
- No capital, sizing, leverage, promotion or order behavior changes.
- Grid remains retired/no-go.
- Deployment validation must retain all existing paper/live safety flags as
  disabled and use only an isolated, no-network, read-only test container.

## Remaining work

This guard is intentionally not a retry mechanism. A future research campaign
must still be a materially distinct economic hypothesis, register through the
normal validation workflow, and pass all data, net-cost, walk-forward, stress
and immutable-holdout gates before any shadow consideration.
