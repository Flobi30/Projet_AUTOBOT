# P4 Shadow Sync Persistent Score Feed Non-Regression - 2026-07-02

## Verdict

PASS_WITH_WARNINGS

## Scope

This patch makes P4 observable in the daily research workflow:

- High Conviction replay trades can now be synced into the official post-P0/P1 ledger as `shadow_paper` observations.
- Daily research collection can run shadow observation sync from persistent paths, not `/tmp`.
- Trend and Mean Reversion shadow labs preserve opportunity score metadata on future closed trades.
- Opportunity score metadata from governance/decision events can be exposed through the ledger loader and loss diagnostics.
- The research container mounts `data/` so it can append attributed `shadow_paper` rows to `data/autobot_state.db`.

## Files Modified

- `config/research_data_collection.yaml`
- `deploy/systemd/run-autobot-research-collection.sh`
- `src/autobot/v2/governance_observability.py`
- `src/autobot/v2/mean_reversion_shadow_lab.py`
- `src/autobot/v2/orchestrator_async.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/shadow_observation_sync.py`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/strategy_governance.py`
- `src/autobot/v2/trend_shadow_lab.py`
- `tests/paper/test_shadow_observation_sync.py`
- `tests/research/test_daily_data_collection_runner.py`
- `tests/test_mean_reversion_shadow_lab.py`
- `tests/test_trend_shadow_lab.py`

## Safety Confirmation

- No live trading flags were changed.
- No paper capital execution path was enabled.
- No order routing behavior was changed.
- No strategy was promoted.
- Grid remains blocked/archived by policy.
- `opportunity_scoring` remains metadata/filter context, not an alpha strategy.
- The daily research service can write only attributed `shadow_paper` ledger rows; it does not mount secrets, logs, or live control files.

## Tests Run

```powershell
python -m py_compile src\autobot\v2\research\daily_data_collection_runner.py src\autobot\v2\trend_shadow_lab.py src\autobot\v2\mean_reversion_shadow_lab.py src\autobot\v2\orchestrator_async.py src\autobot\v2\paper\shadow_observation_sync.py
bash -n deploy/systemd/run-autobot-research-collection.sh
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\test_trend_shadow_lab.py tests\test_mean_reversion_shadow_lab.py tests\research\test_daily_data_collection_runner.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_loss_diagnostics.py tests\paper\test_paper_ledger_loader.py tests\paper\test_official_performance.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py tests\test_strategy_governance.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\test_strategy_router.py tests\research\test_strategy_orchestrator.py tests\test_orchestrator_legacy_entry_guard.py -q
python -m compileall -q src
git diff --check -- <modified files>
```

Results:

- Targeted P4 shadow sync tests: 31 passed.
- Paper diagnostics/ledger tests: 15 passed.
- Governance/registry/CLI tests: 50 passed.
- Router/orchestrator tests: 26 passed.
- Compileall passed.
- Shell script syntax passed.
- Diff check passed with Windows CRLF warnings only.

## Warnings

- The next daily research run must confirm that the VPS service user can write both the shadow report folder and `data/autobot_state.db`.
- High Conviction will still write no observations if the replay produces no closed trades; this is expected and reported as a diagnostic instead of forcing synthetic trades.
- Score buckets are only as useful as the upstream opportunity metadata available in `decision_ledger` or shadow lab rows.

## Next Step

Deploy the patch, verify GitHub/VPS/container commit parity, then let the next daily research runner produce P4 observations before starting P5 diagnostics.
