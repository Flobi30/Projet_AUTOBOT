# AUTOBOT Block 1 — point-in-time parity and regime trial boundary — 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`.

This increment remains research-only.  It hardens the evidence needed before a
feature bundle or regime analysis can support later research decisions; it does
not make any strategy eligible for paper capital, promotion, or live trading.

## Scope delivered

- Canonical feature snapshots now use full streaming batch/shadow parity by
  default.  The former bounded deterministic sample remains available only as
  explicitly labelled diagnostic evidence and can never prove runtime parity.
- The feature registry compares batch and incremental-replay values as streams,
  avoiding an unbounded second materialisation during parity validation.
- Canonical OHLCV rejects explicit naive availability, bar-close, and ingestion
  timestamps rather than silently treating them as UTC.
- The data-capability scanner reports freshness from the latest valid
  `available_time` instead of artifact file modification time.  Artifact age
  remains a separate operational observation, so copying an old historical
  file cannot make it look like fresh market data.
- The fixed baseline regime engine is independent of runtime environment
  settings.  A custom engine or segmentation must provide an active experiment,
  matching snapshot, and registry; the segmentation and feature-config
  fingerprints are then recorded as one idempotent optimization trial before
  enrichment is returned.

## Evidence and tests

- focused Block 1 data/feature/regime suite: `151 passed`;
- full repository collection: `1974 collected, 2 deselected`;
- full suite: `1968 passed, 6 skipped, 2 deselected`;
- `python -m compileall -q src`: passed;
- `git diff --check`: passed (only local CRLF conversion notices).

The code changes are confined to research data, feature, experiment-registry
and tests.  They do not import the router, executor, paper engine, Kraken
private API, or runtime orchestrator.

## Safety invariants preserved

- no paper capital, live trading, automatic promotion, sizing or leverage flag
  was changed;
- no order, execution, private API, or runtime scheduler path was called;
- grid remains retired from execution;
- the scanner distinguishes historical coverage from current availability and
  does not infer readiness from an artifact timestamp alone.

## VPS deployment status

Deployment and smoke evidence are deliberately deferred: Hetzner maintenance
currently prevents safe VPS access.  No VPS checkout, Docker image, service,
database, runtime flag, or research dataset was modified by this increment.

When maintenance ends, the required follow-up is a controlled fast-forward,
`bash deploy/rebuild-autobot-image.sh`, then
`bash deploy/verify-autobot-runtime-evidence.sh`, followed by commit alignment,
health, WebSocket, observation-only flags, and no-order evidence checks.

## Remaining gate

Layer coverage remains `PARTIAL` until the same source revision has controlled
VPS runtime evidence.  This work does not assert that derivative data is
sufficient for a funding/basis hypothesis; insufficient coverage must continue
to produce `DATA_MISSING` or `WAITING_FOR_MORE_DATA`.
