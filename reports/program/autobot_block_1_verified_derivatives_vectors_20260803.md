# AUTOBOT Block 1 — Verified Derivatives Feature Vectors (2026-08-03)

## Decision

`GO_LOCAL_ONLY` — a forward-captured derivatives feature bundle can now be
read as a material-verified `VerifiedFeatureVector` at the research/shadow
boundary. This is a data-contract capability only; it does not start a
strategy or enable any execution mode.

## Finding

The Kraken Futures collector and canonical derivatives snapshots already
preserved funding, basis and open-interest facts. The generic contracts also
provided a verified feature vector, but there was no strict reader joining the
two. A consumer could therefore only carry declared feature versions, not an
immutable, point-in-time subset of a materially verified derivatives bundle.

## Change

- Added `load_verified_feature_vector_from_derivatives_snapshot()`.
- The reader accepts only a `READY`, `forward_capture_only`, material-verified
  and runtime-parity-proven bundle.
- It returns one vector for one explicit Kraken Futures perpetual market,
  timeframe and event time, with only feature values available at
  `observed_at`.
- It retains the perpetual market identity and quote currency. A
  `PF_XBTUSD` vector remains `BTC/USD`; no implicit conversion or executable
  mapping to `BTCZEUR` is created.
- Rows must be `READY`, finite, version-matched, unique and bound to the same
  source snapshot. A conflicting market mapping fails closed.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/research/test_derivatives_feature_snapshot.py \
  tests/research/test_feature_registry.py \
  tests/research/test_verified_feature_vector.py \
  tests/research/test_verified_feature_vector_publication.py \
  tests/research/test_funding_basis_research_adapter.py -q
```

Result: `40 passed`.

The regression coverage proves forward-only provenance, material verification,
point-in-time availability, version binding, immutable perpetual USD identity
and rejection of a mapping conflict. The same scan found no order-router,
paper-trading or execution imports in the new reader.

## Safety

- No strategy, scheduler, router, paper-capital, live, promotion, sizing or
  leverage path changed.
- No public/private trading endpoint is called.
- Grid remains retired/no-go.
- No SSH, VPS, Docker, database or runtime flag operation was attempted while
  the VPS is unavailable.

## Residual Risk

The reader is intentionally dormant until the VPS collector supplies a real
forward-captured bundle with adequate basis/open-interest history. It does not
combine a derivatives vector with a spot vector, generate an alpha signal or
make a strategy eligible for shadow; those remain separate gated work.
