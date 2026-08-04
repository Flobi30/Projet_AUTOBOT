# AUTOBOT engineering rules

## Authority

Use this order when sources disagree: `docs/architecture/AUTOBOT_FOUNDATION.md`,
the versioned strategy registry and mandates, tested code, then dated reports.
Runtime data and dashboards are observations, not policy.

## Non-negotiable safety

- Keep live trading, paper capital and automatic promotion disabled unless the
  user explicitly authorizes a separate change.
- `PROGRAM_EXECUTION_LOCKED` keeps the programme research/shadow-only. Do not
  add an environment-only bypass; lifting it requires a separately reviewed
  source change, human paper review and fresh VPS evidence.
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

## Standard verification commands

Run these from the repository root before a merge or deployment. Start with
the focused suite for the touched boundary, then run the full suite before a
runtime image is rebuilt.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/research -q
$env:PYTHONPATH='src'; python -m pytest -q
python -m compileall -q src tools
git diff --check
```

When Docker is available, the dedicated hermetic image is the reproducible
environment for the complete suite. It has no runtime-data or secret mount and
must run without network access:

```bash
docker build --pull=false --tag autobot-test:local -f Dockerfile.test .
docker run --rm --network none --cpus 0.50 --memory 1g --pids-limit 256 autobot-test:local
```

Do not treat a missing dependency in a global Python installation as a project
test failure; use the locked test image or install `requirements/tests.txt` in
an isolated local environment instead.

For VPS validation, deploy only with `bash deploy/rebuild-autobot-image.sh`,
then confirm the image revision, `/health`, the observation-only flags and
the absence of private execution credentials. Analyses that consume existing
data must run in an isolated no-network container with no runtime state
database or secret mount. Public-data collectors are the explicit exception:
they may use network access only to their documented public endpoints and
must still have no secret or runtime-state mount.

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
