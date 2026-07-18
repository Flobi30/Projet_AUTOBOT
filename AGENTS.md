# AUTOBOT engineering rules

## Authority

Use this order when sources disagree: `docs/architecture/AUTOBOT_FOUNDATION.md`,
the versioned strategy registry and mandates, tested code, then dated reports.
Runtime data and dashboards are observations, not policy.

## Non-negotiable safety

- Keep live trading, paper capital and automatic promotion disabled unless the
  user explicitly authorizes a separate change.
- A strategy produces signals only. It cannot create fills, manage capital or
  bypass independent risk review.
- `OrderIntent` is non-executable. Only `RiskDecision` may lead to an
  `ExecutionCommand`.
- Grid and aliases are `retired_from_execution`; archived replay requires an
  explicit research command.
- Never expose or commit secrets, SSH keys, API keys or runtime databases.

## Working agreement

- Develop in a clean worktree, not the running VPS checkout.
- Preserve untracked runtime artefacts and the current state before deploying.
- Use contract tests at every cross-layer boundary.
- Run focused tests first, then unit/integration regressions, then a VPS smoke.
- A layer is `VERIFIED` only when code, reproducible test and runtime evidence
  are all linked in `docs/architecture/layer_coverage.json`.

## VPS deployment provenance

- Do not use a bare `docker compose build autobot` for AUTOBOT deployments.
  Run `bash deploy/rebuild-autobot-image.sh` from a checked-out VPS revision;
  it embeds and verifies the source commit in the image.
- The daily research collector rejects an image whose revision label differs
  from the VPS checkout. Do not rebuild or retag that image while a daily
  research collection is active: wait for its completion, or stop the
  research-only job cleanly before deploying.
- Runtime reports and research memory may be dirty or untracked on the VPS.
  They are not build inputs and must be preserved; only tracked or untracked
  files that affect the Docker build context block a provenance build.
