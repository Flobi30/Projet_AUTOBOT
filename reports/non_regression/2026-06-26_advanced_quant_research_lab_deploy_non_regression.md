# Advanced Quant Research Lab Deploy Non-Regression - 2026-06-26

## Verdict

`PASS_WITH_WARNINGS`

## What Changed

Commit deployed to VPS:

`5a9973f6e041fa12df8df806afb41982aac516fa`

Files changed by the deployed commit:

- `src/autobot/v2/research/advanced_market_analysis.py`
- `src/autobot/v2/research/statistical_validation.py`
- `src/autobot/v2/research/strategy_orchestrator.py`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/research/__init__.py`
- `tests/research/test_advanced_market_analysis.py`
- `tests/research/test_statistical_validation.py`
- `tests/research/test_strategy_orchestrator.py`
- `reports/research/advanced_quant_research_lab_2026-06-26.md`
- `reports/non_regression/2026-06-26_advanced_quant_research_lab_non_regression.md`

## VPS Deployment Checks

- VPS Git HEAD: `5a9973f6e041fa12df8df806afb41982aac516fa`
- Docker image rebuilt: yes
- New image id: `sha256:05718b9901e20bfceef9fecf8eac715912a325e534e33e210c73854daa04bd11`
- Runtime container restarted: no
- Runtime container status: healthy
- `/health`: healthy
- WebSocket: connected
- Instances: 14

## Safety Checks

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_LIVE_TRADING`: unset/not present
- `ENABLE_INSTANCE_SPLIT_EXECUTOR`: unset/not present
- No live order pattern found in recent logs.
- No Kraken order submission pattern found in recent logs.
- No strategy promotion was performed.
- No paper official execution path was changed.
- No instance child was created.

## Tests

Local pre-deploy validation:

- `python -m py_compile` on touched modules/tests: pass
- `python -m compileall -q src`: pass
- `python -m pytest tests/research/test_advanced_market_analysis.py tests/research/test_statistical_validation.py tests/research/test_strategy_orchestrator.py -q`: `21 passed`
- `python -m pytest tests/research tests/test_v2_cli.py -q`: `225 passed`

VPS post-deploy smoke:

- New image isolated `py_compile`: pass

## Risks Remaining

- The currently running AUTOBOT container was not restarted, so the new research-only image is built but not loaded by the runtime process.
- This is intentional for safety because the change is research-only and the current runtime is healthy.
- If the daily research runner uses the rebuilt image, it can consume the new modules without touching the trading runtime.

## Recommendation

Proceed to observation. If the user wants runtime APIs or scheduled jobs inside the main container to load the new research-only modules, perform a separate controlled restart with a normal post-restart health check.

