# AUTOBOT Block 6 — Fail-closed incident/risk bridge (2026-07-16)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

Runtime-health incidents can now be normalized and consumed by the existing
research/shadow risk mandate boundary. The bridge is side-effect free; it does
not import a router, paper engine or signal handler.

## Behaviour

- `DATA_STALE`, `WEBSOCKET_DISCONNECTED`, `API_UNAVAILABLE` and
  `SQLITE_LOCKED` can only block new risk or reduce the autonomous envelope.
- `DISK_FULL`, `ORDER_UNKNOWN` and `RECONCILIATION_REQUIRED` escalate to
  `KILL` because state persistence or reconciliation cannot be trusted.
- Duplicate incident observations are normalized deterministically.
- Unknown incidents fail closed at the health-contract boundary.
- Existing hard health failures such as a weak rolling PF, negative
  expectancy, ledger error or explicit kill still remain `KILL`; they were not
  weakened to `REDUCE`.

## Safety

- `paper_capital_allowed=false`, `live_allowed=false` and `promotable=false`
  remain invariant on every decision.
- Risk increases and reactivation remain human-review-only.
- This change supplies a typed boundary for future runtime health integration;
  it does not activate runtime execution.

## Evidence

- Focused resilience/risk/shadow tests: `54 passed`.
- Full repository suite: `1550 passed, 5 skipped, 1 existing dependency
  deprecation warning`.
- `python -m compileall -q src`: passed.
- `docs/architecture/layer_coverage.json`: parsed successfully.
- `git diff --check`: passed.

## Deployment status

The commit is ready for controlled deployment together with the preceding
SQLite-backup readiness commit. VPS deployment remains pending because the SSH
key path is not available in the current desktop environment.
