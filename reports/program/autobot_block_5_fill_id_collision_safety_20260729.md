# AUTOBOT Block 5 — Immutable Fill-ID Collision Safety (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the research/shadow OMS ledger now fails closed when an
existing fill identifier is reused with different economic evidence.

## Finding

The append-only fill ledger treated any existing `fill_id` as an idempotent
retry. It did not compare the stored fill or costs with the retry payload.
Its `INSERT OR IGNORE` path could also hide a concurrent identifier collision.
That can mask a quantity, price, fee or provenance discrepancy and corrupt
reconstruction, reconciliation and TCA interpretation.

## Change

- Exact serialized `FillEvent` and cost evidence are now compared for every
  pre-existing `fill_id`.
- Only an exact retry returns `False` as idempotent.
- A divergent fill or cost payload raises `OMSLedgerError` before any order
  event, position or TCA-relevant state changes.
- The persistence path uses an explicit insert. A concurrent uniqueness
  collision is re-read and receives the same exact-retry-or-reject decision.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_oms_ledger.py \
  tests/research/test_runtime_oms_ledger_audit.py \
  tests/research/test_contract_shadow_pipeline.py \
  tests/research/test_runtime_oms_ledger_migration_plan.py -q
```

Result: `42 passed`.

The added regression checks duplicate retries, divergent price/quantity and
fee collisions, restart behavior, immutable ledger counts and reconstructed
position stability.

## Safety

- This is a hermetic research/shadow ledger change only.
- No runtime router, paper-capital, live, promotion, sizing or leverage path
  changed.
- No SSH, VPS, Docker, database or runtime flag operation was attempted while
  the VPS is unavailable.

## Residual Risk

This local ledger remains a research/shadow model. Exchange-side order lookup
and independent runtime reconciliation remain deferred until the VPS is
available and a separate human-reviewed paper scope exists.
