# Non-Regression: Research Memory + Registry Consolidation - 2026-07-01

Verdict: PASS_WITH_WARNINGS

## Scope

- Stabilized the isolated daily research runner after `status=137` OOM.
- Added a normalized strategy registry record and stricter paper-capital gate.
- Kept Grid archived/no-go and non-executable by default.
- Performed safe cleanup only: Docker build cache and temporary smoke YAML.
- No live trading, no paper runtime promotion, no sizing/risk change, no Kraken order.

## Files Changed

- `deploy/systemd/run-autobot-research-collection.sh`
  - Replaced fixed `--memory 768m` with `AUTOBOT_RESEARCH_MEMORY_LIMIT`, default `1536m`.
  - Kept CPU default equivalent via `AUTOBOT_RESEARCH_CPU_LIMIT`, default `0.50`.
- `src/autobot/v2/strategy_validation_registry.py`
  - Added `StrategyRegistryRecord`.
  - Added `normalize_strategy_record`, `build_strategy_registry_records`, and `evaluate_paper_capital_gate`.
  - Paper capital now requires explicit `strategy_id`, execution-ready status, PF > 1, positive expectancy, net PnL, drawdown under threshold, cost evidence, baseline, and OOS evidence.
- `src/autobot/v2/strategy_runtime_policy.py`
  - Added `GRID_RUNTIME_ENABLED` visibility.
  - Effective Grid runtime remains disabled even if the flag is accidentally set.
- `tests/test_strategy_validation_registry.py`
  - Added tests for PF gate, required `strategy_id`, cost evidence, normalized paper eligibility, and Grid runtime retirement.

## Local Validation

- `bash -n deploy/systemd/run-autobot-research-collection.sh`: PASS
- `python -m compileall -q src`: PASS
- `$env:PYTHONPATH='src'; python -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/paper/test_paper_trading_engine.py tests/research/test_archived_grid_defaults.py -q`: 33 passed
- `$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q`: 229 passed

Note: local compile changed tracked `.pyc` files. They were not committed and were not deleted, matching the safe-cleanup rule. A later dedicated `.gitignore`/untrack cleanup can handle those.

## GitHub / VPS

- Commit pushed: `dbc3964`
- VPS repo after deployment: `dbc3964`
- Main trading container was not restarted.
- Research image rebuilt so the isolated research service sees the new source.

## OOM Root Cause And Fix

- Previous failed run: `autobot-research-data.service` exited with `status=137`.
- Kernel/container evidence indicated the research container was killed near the old cgroup limit, about 768 MiB / 783 MB RSS.
- Fix scope is limited to the research container:
  - Old effective memory: `805306368` bytes, about 768 MiB.
  - New effective memory: `1610612736` bytes, 1.5 GiB.
  - CPU remains `NanoCpus=500000000`, equivalent to 0.50 CPU.
- No paper/live/runtime trading behavior was changed.

## Safe Cleanup

- Docker builder cache reclaimed:
  - Initial cleanup reclaimed about 9.222 GB.
  - Follow-up build-cache cleanup reclaimed about 963 MB.
- Removed `/tmp/smoke_strategy_edge_*.yaml`.
- Kept:
  - `data/autobot_state.db`
  - `data/paper_trades.db`
  - `reports/research/*`
  - `backups/*`
  - `.env`, keys, useful logs, historical research outputs
- Post-cleanup disk:
  - `/dev/sda1`: 6.4G used / 66G available / 9% used
  - Docker build cache: 0B

## VPS Runtime Validation

- `/health`: `healthy`
- Orchestrator: `running`
- WebSocket: `connected`
- Instances: 14
- Docker main container: `autobot-v2` running, healthy
- Runtime flags observed:
  - `PAPER_TRADING=true`
  - `LIVE_TRADING_CONFIRMATION=false`
  - `COLONY_AUTO_LIVE_PROMOTION=false`
  - `STRATEGY_ROUTER_LIVE_ENABLED=false`
- No critical research-service logs after the fixed run.
- No critical/traceback/live-order log lines detected from the main container in the final check window.

## Research Runner Validation

- Service: `autobot-research-data.service`
- Result: `success`
- ExecMainStatus: `0`
- Final state: `inactive/dead`, expected for oneshot after completion.
- Generated run id: `daily_2026_07_01T14_49_38Z`
- Generated key artifacts:
  - `reports/research/daily_data_collection/daily_2026_07_01T14_49_38Z/daily_2026_07_01T14_49_38Z_daily_collection.md`
  - `reports/research/daily_data_collection/daily_2026_07_01T14_49_38Z/daily_2026_07_01T14_49_38Z_daily_collection_manifest.json`
  - `reports/research/high_conviction_walk_forward/daily_2026_07_01T14_49_38Z_high_conviction_walk_forward.json`
  - `reports/research/high_conviction_walk_forward/daily_2026_07_01T14_49_38Z_high_conviction_walk_forward.md`
  - `reports/research/strategy_orchestrator/daily_2026_07_01T14_49_38Z_strategy_orchestrator.json`
  - `reports/research/strategy_orchestrator/daily_2026_07_01T14_49_38Z_strategy_orchestrator.md`
  - `reports/research/strategy_edge/daily_2026_07_01T14_49_38Z/strategy_edge_improvement_2026_07_01.json`
  - `reports/research/strategy_edge/daily_2026_07_01T14_49_38Z/strategy_edge_improvement_2026_07_01.md`
  - `data/research/daily/microstructure/daily_2026_07_01T14_49_38Z/daily_2026_07_01T14_49_38Z_spread_depth_spread_depth.csv`

## Trading Safety

- No live flag was enabled.
- No paper/live strategy was promoted.
- No Grid reactivation.
- No instance split or child instance executor activation.
- No runtime sizing or risk change.
- No Kraken order was created.

## Warnings / Residual Risk

- The main `autobot-v2` container was intentionally not restarted, so runtime trading behavior is unchanged. The registry consolidation code is deployed in Git and built into the latest image for research usage; it will only affect the main runtime after a future explicit runtime rollout.
- Some tracked `.pyc` files remain dirty locally after compile. They were intentionally excluded from this patch.
- Daily collection still reports expected `duplicates_deduped`, `bid_ask_absent`, and `order_book_depth_absent` on OHLCV bars; spread/depth is collected separately through the research microstructure recorder.

## Next Recommended Action

Continue observing daily research reports. A future explicit runtime rollout can wire the consolidated registry status into dashboard/API surfaces, but no paper/live allocation should be enabled until strategy evidence satisfies the new gate.
