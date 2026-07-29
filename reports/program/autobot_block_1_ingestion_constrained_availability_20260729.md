# AUTOBOT Block 1 — Ingestion-Constrained Canonical Availability (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — canonical OHLCV rows now preserve a point-in-time-safe
availability time when a historical import records its ingestion time but does
not provide an independent source availability time.

## Finding

The feature registry already used the maximum of a row's declared
`available_time` and `ingestion_time`.  That protected registered features,
but the canonical CSV itself could label a backfilled bar as available at bar
close.  A future consumer that read only the canonical dataset could therefore
mistake historical backfill for real-time availability.

## Change

- When a source supplies `available_time`, it remains authoritative, bounded
  below by the completed bar close.
- When source availability is absent but aware ingestion time is present,
  canonical availability becomes `max(bar_close_time, ingestion_time)` and is
  labelled `DERIVED_BAR_CLOSE_CONSTRAINED_BY_INGESTION` /
  `HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION`.
- The legacy canonical adapter applies the same rule when a recorded ingestion
  time is supplied, rather than preserving a false close-time availability.
- Existing snapshots retain the feature registry's ingestion-time guard.
  They should be re-canonicalized by a future controlled data job before being
  treated as standalone point-in-time inputs.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_canonical_ohlcv_store.py \
  tests/research/test_feature_registry.py \
  tests/research/test_canonical_feature_snapshot.py \
  tests/research/test_data_capability_scanner.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted Block 1 regression: `54 passed`;
- diff check: PASS.

The new boundary tests prove that a known later ingestion time constrains both
new canonical rows and migrated legacy rows.  Explicit source availability is
still preserved, and missing temporal evidence remains explicitly labelled
rather than inferred.

## Safety and deployment

- data/research canonicalization only; no strategy or runtime order path
  changed;
- no VPS/SSH action while Hetzner is unavailable;
- no paper capital, live execution, promotion, sizing or leverage change;
- Grid remains retired from execution.

## Residual risk

Canonical data imported before this correction may still carry a close-time
availability label.  Existing feature computation remains protected by its
effective availability-time guard, but future VPS recovery should schedule a
bounded re-canonicalization and manifest validation before these snapshots are
used by any new research consumer.
