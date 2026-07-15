# AUTOBOT Block 4 — Feature Evidence Data Identity — 2026-07-15

## Decision

`GO` for further research-only hardening. No shadow runtime was started and no
paper capital, promotion, leverage, sizing change or live trading was enabled.

## Change

The feature evidence carried by a future shadow artifact must now reproduce its
`data_snapshot_id` exactly:

- one feature bundle uses its canonical source snapshot id;
- the supported spot-plus-derivatives composition reproduces the deterministic
  combined snapshot identity used by manifested experiments;
- duplicate, overlapping or unsupported feature-bundle compositions fail
  closed;
- an artifact cannot claim an unrelated data snapshot while preserving the
  same feature versions.

This extends the previous immutable feature-snapshot binding without adding
database lookups or order execution to the runtime hot path.

## Evidence

- Functional commit: `a731eb767cf380b51b1f852a4404564a6181830d`.
- Targeted affected-boundary suite: `59 passed`.
- Research suite: `396 passed`.
- Compile and diff checks: passed.
- Isolated immutable VPS release suite: `1591 passed` in 70.32 seconds.
- The same four pre-existing pytest warnings remain in non-async tests marked
  with `asyncio` in `src/autobot/v2/tests/test_order_router.py`.
- Deployment smoke: source at the functional commit, rebuilt `autobot-v2`
  healthy, `/health` healthy, WebSocket connected and 14 instances observed.
- Safety gates: paper execution adapter, live confirmation, live strategy
  routing, automatic promotion and instance splitting all remain disabled.

## Residual scope

The legacy runtime still produces only a blocked non-executable contract
preview. A later, separately reviewed integration may use these checks to
create a real shadow observation, but must not bypass the read-only artifact
resolver, risk boundary or ledger contract.
