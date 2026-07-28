# AUTOBOT Block 6 — Deployment Evidence Gate — 2026-07-29

## Decision

`REWORK_FOR_VPS_VALIDATION`

The local readiness gate is complete and intentionally non-authorizing. It
cannot make AUTOBOT ready for paper capital, live trading, or strategy
promotion. A controlled VPS deployment and fresh runtime evidence remain
required.

## Change

The paper-readiness dossier now requires a `RuntimeDeploymentEvidence` record
before it can report `READY_FOR_HUMAN_PAPER_REVIEW`.

The evidence must prove all of the following from one fresh observation:

- the same commit on the requested source, GitHub, VPS checkout and container
  image;
- healthy container and `/health` endpoint;
- connected WebSocket;
- observation-only runtime;
- paper capital, live trading and automatic promotion all disabled.

Missing, stale, mismatched or malformed evidence is a blocking result. The
dossier itself remains unable to authorize paper, live or promotion even if it
is constructed directly.

## Local proof

- Commit with code gate: `11c706430f1c54bebf8aa0b3d4254913c1182cbe`
- Documentation follow-up: `e6cc181a8733a12894b73337cfedfb0038f1c96f`
- Focused resilience/deployment suite: `27 passed`
- Research suite: `695 passed, 1 skipped`
- Full test suite: `1314 passed, 1 skipped`
- `mypy --follow-imports=skip src/autobot/v2/research/resilience_readiness.py`: passed
- Flake8 and `compileall`: passed
- `git diff --check`: passed before commit

## VPS evidence

The controlled read-only SSH check to `autobot-vps` timed out on port 22 on
2026-07-29. No deployment, restart, Docker command, data collection, order
path or runtime-flag change was attempted after that failure.

The VPS/container therefore must not be claimed to run either commit above
until SSH is restored and the controlled deployment smoke has completed.

## Safety

- No paper capital enabled.
- No live trading enabled.
- No automatic promotion enabled.
- No sizing or leverage changed.
- No order, paper-order or private Kraken endpoint called.

## Required follow-up

1. Restore normal SSH reachability to `autobot-vps`.
2. Fast-forward the VPS checkout to the current GitHub `master` commit.
3. Rebuild using `bash deploy/rebuild-autobot-image.sh` only.
4. Capture fresh `RuntimeDeploymentEvidence` from the GitHub/VPS/container
   alignment, health, WebSocket and non-authorizing runtime flags.
5. Run exactly one bounded research-only smoke after the deployment checks.
