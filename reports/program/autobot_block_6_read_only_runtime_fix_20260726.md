# Block 6 — Read-only runtime corrective, 2026-07-26

## Decision

`REWORK → GO` after the observation-runtime hardening smoke test exposed a
previously implicit write to `/app/autobot_async.log`.  The container root is
intentionally read-only; application logs must use the explicit `/app/logs`
runtime volume.

## Change

- the production image sets `AUTOBOT_LOG_FILE=/app/logs/autobot_async.log`;
- developer runs default to `logs/autobot_async.log` rather than the working
  directory root;
- deployment tests assert that the configured log path and writable volume
  remain aligned.

No execution, paper-capital, live, promotion, sizing, leverage, strategy, or
dashboard behavior changed.

## Local evidence

- `python -m compileall -q src` passed;
- deployment, observation-boundary, and main-runtime targeted tests: 16
  passed;
- full regression suite rerun after the corrective change;
- `git diff --check` passed (line-ending notices only).

## VPS acceptance criteria

The deployment is accepted only if the rebuilt container:

1. is healthy and the orchestrator is running;
2. uses the image matching the Git commit;
3. has a read-only root filesystem with `/app/logs` mounted writable;
4. has no `KRAKEN_API_KEY` or `KRAKEN_API_SECRET` environment variable;
5. remains observation-only with all paper/live execution guards disabled.

## Residual risk

The change deliberately protects only the application log write identified by
the smoke test.  Future attempts to write elsewhere in the image root must
fail closed and be corrected toward an explicit runtime volume rather than by
weakening the container hardening.
