# Instance Split Safety Deploy Non-Regression - 2026-06-15

## Verdict

**PASS**

Commit `a72ac9bf88eab06da2de867a0ab412925734b44e` was deployed to the VPS with
the instance split executor disabled.

## Deployment

- VPS repository: `/opt/Projet_AUTOBOT`
- Branch: `master`
- Deployed commit: `a72ac9bf88eab06da2de867a0ab412925734b44e`
- Docker service rebuilt without cache and recreated successfully.
- VPS targeted tests: `43 passed`.
- VPS `python3 -m compileall -q src`: PASS.

## Runtime health

- Container: `healthy`
- `/health`: `healthy`
- Orchestrator: `running`
- WebSocket: `connected`
- Instances: `14`
- Startup tracebacks/critical/fatal errors: none
- One `WS high_message_rate` warning was observed with `drops=0`; it is not
  related to instance splitting and did not affect health.

## Trading safety

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` is unset on the VPS and resolves to `false`.
- Runtime split policy reports:
  - `executor_enabled=false`
  - `paper_mode_only=true`
  - required strategy status: `paper_validated`
- `instance_lineage` rows after restart: `0`
- No child instance was created.
- No live order path was enabled.
- No strategy was promoted.
- Sizing, risk, leverage and strategy logic were unchanged.

## Conclusion

The safety patch is active. Duplication remains inert during normal paper
training. The isolated mechanics test is available, but runtime duplication
must stay disabled until a strategy has completed official paper validation
and a dedicated disposable-parent paper sandbox campaign is approved.
