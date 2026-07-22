# AUTOBOT Block 4 — Offline Shadow Provenance Bridge — 2026-07-22

## Decision

**GO (research/shadow evidence only).**

This increment closes a boundary gap without starting a runtime service or
changing any execution behaviour. It adds one explicit, offline-only hand-off
between a registered shadow artifact and an atomically published canonical
feature vector. It is not a paper-capital, live or order-routing feature.

## Commit

Implementation commit: `2978f28` (`Bind verified canonical features to offline shadow previews`).

## What changed

- Added `offline-shadow-provenance-bind`, a CLI command that reads an eligible
  strategy artifact from the append-only registry in SQLite read-only mode and
  re-verifies one published feature vector against its canonical bundle.
- Added `OfflineShadowProvenanceBinding`, which emits metadata accepted only by
  the already blocked runtime shadow-preview contract.
- V1 requires exactly one feature snapshot and exactly one common observation
  time. It rejects stale data, snapshot/version mismatches, expired mandates
  and a notional above the shadow mandate.
- Added a full-artifact read-only resolver while retaining the existing smaller
  `StrategyArtifactReference` resolver for generic contract consumers.
- Documented the boundary in the architecture foundation and coverage matrix.

## Invariants verified

- The bridge imports no router, executor, paper engine, signal handler or
  orchestrator.
- It cannot start runtime, create an order, enable paper capital, enable live
  trading or promote an artifact.
- Grid remains retired through the pre-existing artifact governance boundary.
- Multi-source spot/derivatives bindings remain blocked in V1 until a future
  increment proves a coherent common observation time.

## Local evidence

Commands passed:

```text
python -m compileall -q src
PYTHONPATH=src python -m pytest \
  tests/test_contracts.py \
  tests/research/test_contract_shadow_pipeline.py \
  tests/research/test_canonical_feature_snapshot.py \
  tests/research/test_verified_feature_vector.py \
  tests/research/test_verified_feature_vector_publication.py \
  tests/research/test_shadow_observation_ledger.py \
  tests/research/test_shadow_governance.py \
  tests/research/test_runtime_shadow_preview.py \
  tests/research/test_execution_simulator.py \
  tests/test_signal_handler_async_unit.py \
  tests/test_v2_cli.py -q
```

Result: `152 passed`.

Full local suite: `1842 passed, 6 skipped`.

`git diff --check` passed and the changed non-test files passed a focused
secret-pattern scan.

## VPS deployment evidence

The implementation and this report were deployed with provenance rebuilds.
For the implementation deployment, GitHub, VPS checkout, image and
`autobot-v2` container were aligned to `6dfbfdf32b22bb0b5fed004b11acc1d155d6af3a`.

- `autobot-v2`: `running healthy`
- `/health`: healthy; orchestrator running; WebSocket connected; 14 instances
- all nine research timers: active
- isolated deployed-image smoke: `162 passed`
- resource observation after smoke: 10.37% CPU and 98.48 MiB / 3 GiB memory
- all paper execution, auto-promotion and live-routing flags: `false`
- recent logs: no live-order, Kraken-live, live-activation or paper-capital
  activation evidence

The VPS worktree retains 13 pre-existing runtime artifacts. They were neither
reset nor included in the image build.

## Residual risks

- The bridge is intentionally outside the hot runtime. It proves an offline
  canonical-to-preview hand-off, not direct runtime-feed parity.
- No strategy has been made eligible for paper capital or live trading.
- A future multi-source binding requires explicit, common point-in-time proof;
  it must not merge spot and derivatives evidence by timestamp approximation.
