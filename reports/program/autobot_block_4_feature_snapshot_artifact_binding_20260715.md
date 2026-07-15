# AUTOBOT Block 4 — Point-in-Time Feature Evidence Binding — 2026-07-15

## Decision

`GO` for the next research-only hardening step. This change does not start a
shadow runtime and does not authorise paper capital, promotion, leverage,
sizing changes or live trading.

## Gap closed

Canonical feature bundles already recorded point-in-time provenance in batch
research. A future shadow intent, however, previously carried only a snapshot
identifier and feature-version map. It could not prove the immutable feature
bundle that supplied those facts.

## Change

- Added `FeatureSnapshotReference` to the v1 boundary contracts.
- A reference requires a feature snapshot fingerprint, source fingerprint,
  registry fingerprint, feature versions, proven runtime parity and zero
  unknown ingestion timestamps.
- `StrategyArtifact` and `StrategyArtifactReference` now preserve one or more
  non-overlapping feature snapshot references.
- Shadow-capable artifacts built from an experiment now require point-in-time
  feature evidence from the experiment environment.
- A new `OrderIntent` fails closed unless its artifact carries that evidence.
- The existing registry resolver remains read-only and now rejects old or
  incomplete artifact records for a new future shadow intent.

## Deliberate scope limits

- No feature registry or artifact registry lookup was added to the hot signal
  handler.
- Blocked legacy BUY signals still create only a non-executable preview.
- Existing artifacts without the new evidence remain historical and cannot
  create new intents; they are not rewritten.
- No feature value, strategy rule, cost model or execution rule was changed.

## Local evidence

- Targeted contract/governance/preview/OMS suite: `58 passed`.
- Broader feature provenance and affected-boundary suite: `93 passed`.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Release evidence

- Functional commit: `a9211e1aae0edec12f665b2a6167fc21195f0bfa`.
- At the functional deployment, GitHub, VPS source and rebuilt `autobot-v2`
  container used that commit.
- Isolated immutable VPS release suite: `1590 passed` in 70.43 seconds.
- The four warnings are pre-existing non-async tests carrying an asyncio mark
  in `src/autobot/v2/tests/test_order_router.py`; no warning was added here.
- VPS smoke: `/health` healthy, orchestrator running, WebSocket connected and
  14 instances observed.
- Safety gates confirmed: paper execution adapter disabled, live confirmation
  disabled, live strategy router disabled, automatic promotion disabled and
  instance-split executor disabled.
- Filtered container logs contained no traceback, critical trading error, live
  order or live-trading activation.

## Residual risk

The production runtime has not yet been replaced by the v1 research/shadow
path. This is intentional: the new boundary prevents unsupported future shadow
intents but does not activate them.
