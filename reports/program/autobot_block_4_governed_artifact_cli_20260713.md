# AUTOBOT Block 4 — Governed Artifact Registration CLI

## Decision

**GO.** The CLI can now register immutable research artifacts from experiment
evidence without changing runtime behavior.

## Guardrails

- A shadow-capable status requires a terminal, passed `SHADOW_REVIEW` record.
- It also requires an explicit human approval reference.
- The artifact registry re-checks the experiment fingerprint before writing.
- The command never starts a shadow runtime, routes a signal, allocates capital
  or enables paper/live/automatic promotion.
- Grid aliases remain retired through the artifact domain validation.

## Verification

- CLI/governance/experiment focused suite: `51 passed`.
- Compilation and whitespace validation: passed.
- Full isolated VPS suite: `1567 passed` with exit status `0`.
- The VPS runtime was rebuilt/recreated from code commit
  `66ebb8ce8595a68e2c70ac05d16ea28bc4f2dd17` and returned healthy with its
  WebSocket connected and fourteen instances running.
- `PAPER_EXECUTION_ADAPTER_ENABLED=false`,
  `LIVE_TRADING_CONFIRMATION=false`, `STRATEGY_ROUTER_LIVE_ENABLED=false` and
  `COLONY_AUTO_LIVE_PROMOTION=false` after restart.

## Residual constraint

No current experiment has passed the economic data and validation gates. The
command is therefore an audited future handoff mechanism, not an authorization
to activate any strategy.
