# AUTOBOT Block 6 — Observation Service Isolation (2026-07-26)

## Decision

**GO — research/observation runtime only.**

The deployed `autobot` service is an observation-only service.  Its legacy
`PAPER_TRADING` compatibility flag must not imply an executable paper wallet,
private Kraken access, or a real-order path.

## Changes

- The Compose service forces `PAPER_TRADING=false` and
  `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`.
- The service no longer loads `env_file: .env`, mounts `.env`, injects
  `KRAKEN_API_KEY`, or injects `KRAKEN_API_SECRET`.
- The image no longer embeds `.env.example` at `/app/.env`; runtime
  configuration is explicit environment input only.
- The observation service now uses a read-only root filesystem, drops Linux
  capabilities, enables `no-new-privileges`, and receives only a bounded
  writable `/tmp` plus its explicit data/log/report volumes.
- Observation-only startup treats paper/live confirmation as not applicable;
  it still requires dashboard authentication, configured risk limits, public
  connectivity, writable local state/audit paths, clock checks, and an armed
  persistent kill switch.
- Dashboard runtime and position APIs report `observation_only` instead of
  mislabelling this configuration as paper.  They retain
  `configured_paper_mode` separately for legacy-config diagnostics.

## Validation

Local validation:

```text
python -m compileall -q src
PYTHONPATH=src python -m pytest \
  tests/test_deployment_safety_invariants.py \
  tests/test_observation_execution_boundary.py \
  tests/test_trading_debug_endpoint.py -q
# 15 passed

PYTHONPATH=src python -m pytest -q
# 1886 passed, 6 skipped, 2 deselected
```

The static deployment test verifies that the observation service cannot load
the complete `.env` or the two Kraken private credential variables.

## Explicit non-goals

- No paper capital, paper execution, live execution, strategy promotion,
  sizing, or leverage is enabled.
- No private key, API secret, token value, or `.env` content is recorded in
  this report.
- Dashboard network exposure is unchanged in this patch because restricting
  it requires a separate reverse-proxy/access review.

## Residual risks

The next operational hardening item is a documented, tested backup scope that
includes the persistent kill-switch and research registries in addition to the
runtime state database.  It remains research/operations work and is not an
authorization for paper or live trading.
