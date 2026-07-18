# AUTOBOT Block 1 — Verified Feature Vector Selection

## Decision

`GO` for this bounded research-only feature hand-off. Block 1 remains `PARTIAL`.

## Scope

Added a deterministic reader for the latest fully available canonical feature
vector for each explicitly mapped market/timeframe file. It is a batch reader,
not a runtime signal producer and has no dependency on the router, paper
engine, executor or order path.

## Guarantees

- The caller supplies a timezone-aware `observed_at`; no wall-clock time is
  inferred.
- A selected event must be at or before `observed_at`, have every configured
  feature in `READY` status, and have every feature available by
  `observed_at`.
- The canonical bundle is materially re-verified before a vector is returned.
- Requested unavailable symbols or timeframes fail closed.
- A candidate remains a data artifact only: it cannot create an intent, order,
  paper trade, promotion or live action.

## Evidence

- `tests/research/test_canonical_feature_snapshot.py`
  proves selection does not look ahead to the next candle and rejects a market
  with no ready vector.
- `tests/research/test_verified_feature_vector.py`,
  `tests/research/test_shadow_observation_ledger.py` and
  `tests/research/test_runtime_shadow_preview.py` remain in the focused suite.

## Remaining Gate

The runtime has no producer which independently computes and publishes the
same point-in-time feature vectors. That integration remains blocked until a
separate research-safe adapter and replay proof exist. The legacy runtime order
path remains fail-closed and is not changed by this work.

## Safety

- Research-only.
- No paper capital, live trading, promotion, sizing or leverage change.
- No secret, private API or order endpoint use.
- Grid remains retired from runtime execution.
