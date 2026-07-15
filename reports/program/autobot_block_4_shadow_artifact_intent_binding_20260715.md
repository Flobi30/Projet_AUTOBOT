# AUTOBOT Block 4/5 - Shadow Artifact Intent Binding

Date: 2026-07-15
Code commit: `6a05de082af512948110189772a8f4dee70b5e4c`

## Decision

GO for the non-executable contract boundary. REWORK remains required before a
runtime service can create real shadow observations from this boundary.

## Change

- Added `StrategyArtifactReference` to the stable contract layer.
- Every new `OrderIntent` now requires a matching artifact reference in
  addition to its strategy and market identity.
- The reference binds artifact ID, fingerprint, strategy/version, code commit,
  snapshot and feature versions. A mismatch rejects the intent at construction.
- `StrategyArtifact` can generate its reference only from its immutable facts.
- The runtime BUY preview now rejects missing, tampered, non-shadow-eligible
  or inconsistent artifact payloads before it can produce an intent.
- The preview remains diagnostic only: it cannot construct an
  `ExecutionCommand`, submit an order, write the official paper ledger or
  change a risk mandate.

## Validation

- Focused contracts, shadow governance, shadow OMS, execution simulation and
  signal-handler tests: `52 passed`.
- Compilation, secret scan and forbidden runtime-import audit: passed.
- Final disposable Linux release suite: `1586 passed, 4 existing pytest
  warnings` in 70.35 seconds.
- The warnings are existing asyncio marks on synchronous order-router tests;
  none were introduced by this change.

## Runtime Evidence

- GitHub, VPS source and running container code are aligned on
  `6a05de082af512948110189772a8f4dee70b5e4c`.
- `autobot-v2` is healthy; the orchestrator is running, the WebSocket is
  connected and 14 instances are present.
- The new contract modules compile inside the deployed image.

## Safety

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`
- No paper capital, live order, promotion, sizing or leverage change occurred.

## Residual Risk and Next Safe Work

The preview validates an artifact payload is self-consistent, but deliberately
does not open the append-only artifact registry while the runtime is handling
a signal. It therefore does not yet prove the reference was resolved from a
registered artifact. The next safe work is a read-only registry snapshot
resolver, run outside the hot signal handler, followed by a hermetic test that
binds only an existing `SHADOW_ELIGIBLE` or `SHADOW` artifact. No current
strategy has authorization to start that runtime shadow path.
