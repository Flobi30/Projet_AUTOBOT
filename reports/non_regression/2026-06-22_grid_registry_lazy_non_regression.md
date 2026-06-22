# Grid Registry Lazy Loading - Non-Regression (2026-06-22)

## Verdict

PASS

## Scope

The archived Adaptive Grid pair registry is no longer constructed during normal
AUTOBOT startup. It is loaded only by an explicit archived Grid research helper
or the legacy child multi-grid path, neither of which is selected by the current
observation-only runtime policy.

## Safety

- Runtime instances remain `observation_only`.
- Grid remains retired from runtime and available only for research replay.
- No live, paper execution, sizing, risk, promotion, or spin-off flag changed.
- The legacy child multi-grid path remains inactive under the existing split and
  governance gates; its registry is now lazy-loaded if that path is ever reached.

## Validation

- `python -m compileall -q src`: passed.
- Focused regression suite: `224 passed`.
- `docker compose config -q`: passed.
- `git diff --check`: passed.

The regression suite includes an assertion that the active instance factory
cannot construct the archived Grid registry. Post-deploy `/health` and runtime
policy checks are recorded after controlled deployment.
