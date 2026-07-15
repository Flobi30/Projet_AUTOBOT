# AUTOBOT Block 4 - Read-only Shadow Artifact Resolver

Date: 2026-07-15
Code commit: `d6b66697e6b732a266d2a9178311f1a9d4743536`

## Decision

GO for offline artifact binding. No runtime shadow service, paper capital or
live path is enabled by this work.

## Change

- Added `StrategyArtifactRegistry.resolve_shadow_order_intent_reference()`.
- The resolver opens the artifact registry through SQLite `mode=ro` and
  `query_only`, then verifies the serialized artifact's ID and fingerprint.
- It returns a non-executable `StrategyArtifactReference` only for an
  existing `SHADOW_ELIGIBLE` or `SHADOW` artifact.
- `RESEARCH`, `THROTTLED`, `QUARANTINED`, `REJECTED` and `RETIRED` artifacts
  cannot produce a new order intent reference.
- Added `strategy-artifact-resolve-reference` as an offline CLI command. It
  emits provenance evidence only and cannot start a service or route an order.
- The runtime preview now matches this rule and refuses a throttled artifact
  for a new intent.

## Validation

- Focused governance, CLI, preview, contract, OMS and execution-simulation
  tests: `66 passed`.
- The resolver test proves the registry database hash is identical before and
  after resolution.
- Compilation, secret scan and forbidden runtime-import audit: passed.
- Final disposable Linux release suite: `1588 passed, 4 existing pytest
  warnings` in 70.41 seconds.

## Runtime Evidence

- GitHub, VPS source and running container code are aligned on
  `d6b66697e6b732a266d2a9178311f1a9d4743536`.
- `autobot-v2` is healthy; the orchestrator is running, the WebSocket is
  connected and 14 instances are present.

## Safety

- `PAPER_EXECUTION_ADAPTER_ENABLED=false`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false`
- No paper capital, live order, promotion, sizing or leverage change occurred.

## Residual Risk and Next Safe Work

This resolver is deliberately batch-only. There is no approved artifact for a
new runtime shadow observation, and the hot signal handler does not open the
artifact registry. The next safe work is to audit the data- and feature-bundle
resolver that would supply the same point-in-time snapshot to batch validation
and a future shadow worker. It must remain separate from the current runtime
handler and no strategy should be activated merely because this plumbing
exists.
