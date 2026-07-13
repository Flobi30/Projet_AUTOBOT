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

## Residual constraint

No current experiment has passed the economic data and validation gates. The
command is therefore an audited future handoff mechanism, not an authorization
to activate any strategy.
