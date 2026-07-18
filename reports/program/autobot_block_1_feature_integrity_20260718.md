# AUTOBOT Block 1 — Point-in-Time Feature Integrity — 2026-07-18

## Decision

`GO` for the feature-integrity sub-gate. Block 1 remains `PARTIAL`: the
runtime still needs a separately proven live-shadow feature consumer before
the broader shadow-parity gate can be closed.

- Commit: the Git commit that introduces this report; the exact deployed SHA
  is recorded in the VPS validation evidence after deployment.

## Delivered

- Feature availability now uses the later of declared availability and actual
  ingestion time. A backtest cannot see an event before AUTOBOT recorded it.
- Historical feature materialization is compared with an incremental replay,
  rather than a second batch call over reordered rows.
- The feature engine semantics are included in the registry fingerprint. A
  changed availability rule therefore invalidates prior feature provenance.
- Canonical and derivatives feature snapshots are schema v2 bundles: each
  listed CSV is re-hashed, row-count checked and included in a bundle-content
  fingerprint. The logical feature fingerprint and active registry/version
  evidence are recomputed before the bundle is accepted.
- The experiment environment records the verified bundle-content fingerprint;
  a local manifest path is not used as experiment identity.
- A `SHADOW_ELIGIBLE` or `SHADOW` strategy artifact now requires every feature
  snapshot to carry that material-verification proof and bundle-content root.
  Legacy or merely declared research evidence may remain archived, but cannot
  cross the shadow boundary.

## Validation

- Python compilation of all modified research modules and tests: passed.
- Feature, canonical snapshot, derivatives snapshot, manifested experiment,
  bounded coordinator, alpha-runner, shadow-governance and runtime-preview
  regression suite: `73 passed`.
- Tamper tests prove that a changed feature CSV is rejected for both canonical
  and derivatives bundles.
- A CLI governance integration test materializes and independently verifies a
  real canonical feature bundle before registering a shadow-eligible artifact.
- Verified-vector contract, runtime-preview and legacy signal-handler tests:
  `42 passed`.
- Complete hermetic unit suite: `1345 passed, 6 skipped`.
- Complete hermetic integration suite: `313 passed`.
- The incremental replay uses an event-time index with bounded lookback, so a
  historical ingestion batch does not perform a full-history scan for every
  feature value.

## Safety

- Research-only data and provenance code; no runtime order, router, paper
  execution or private Kraken API import was added.
- Paper capital, live, automatic promotion, sizing and leverage remain
  unchanged and disabled.
- Existing v1 feature manifests remain non-shadow-parity evidence. New
  materialized v2 bundles are required for verified provenance.

## Remaining Block 1 Gate

The data and batch-replay boundary is now materially verified and that proof
is mandatory for any new shadow-capable artifact. The non-executable runtime
preview now also rejects an artifact unless it receives one complete immutable
feature vector per verified bundle, with exact values available at the
decision time. The remaining shadow work is to connect this proven preview
boundary to an official observation writer and compare each resulting
observation with the same point-in-time batch decision. This remains
research/shadow-only and does not authorize paper or live execution.
