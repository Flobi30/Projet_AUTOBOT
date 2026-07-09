# Non-Regression - P18A Repo Audit, Safe Cleanup and Alpha Lab

Date: 2026-07-09
Verdict: `PASS_WITH_WARNINGS`

## Scope

P18A added repository audit/cleanup support and a research-only Alpha Hypothesis Lab. No runtime trading code path was enabled.

## Files Added / Changed

Added:

- `src/autobot/v2/research/alpha_hypothesis_lab.py`
- `src/autobot/v2/research/repo_maintenance.py`
- `docs/research/alpha_hypotheses.json`
- `docs/research/alpha_hypotheses.schema.json`
- `docs/research/ALPHA_HYPOTHESIS_LAB.md`
- `tests/research/test_alpha_hypothesis_lab.py`
- `tests/research/test_repo_maintenance.py`
- `reports/research/p18a_audit_2026-07-09.md`
- `reports/research/p18a_cleanup_manifest_2026-07-09.json`
- `reports/research/p18a_inventory_pre_2026-07-09.json`
- `reports/research/p18a_inventory_post_2026-07-09.json`
- `reports/non_regression/2026-07-09_p18a_repo_cleanup_alpha_lab_non_regression.md`

Removed from Git tracking:

- tracked Python bytecode under `src/**/__pycache__/*.pyc`
- tracked validation artifact logs under `artifacts/validation/**`

These are generated artifacts and are ignored or should remain generated-only.

## Cleanup Evidence

Local cleanup manifest:

- manifest: `reports/research/p18a_cleanup_manifest_2026-07-09.json`
- deleted entries: `2148`
- deleted size: `74310025 bytes`
- databases deleted: `false`
- reports deleted: `false`
- backups deleted: `false`
- secrets deleted: `false`

VPS cleanup:

- command: `docker builder prune -af`
- reclaimed: `2.056GB`
- disk after cleanup: `/dev/sda1 75G total, 7.4G used, 65G available, 11% used`
- container remained healthy after prune

## Tests Run

```bash
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_lab.py tests\research\test_repo_maintenance.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper -q
```

Results:

- new P18A tests: `10 passed`
- registry/CLI/grid tests: `46 passed`
- paper tests: `72 passed`
- compileall: OK

## Trading Safety

Confirmed unchanged:

- no live enabled
- no paper capital enabled
- no strategy promotion
- no UI change
- no sizing/leverage change
- grid remains archived/no-go
- trend and mean reversion remain benchmark-only
- high conviction remains research-only

## VPS Runtime Health

Before deploying this commit, VPS runtime was checked:

- current VPS commit before P18A sync: `ba2ffadb0d20c94a266d7605a25dfa40d37489c0`
- container: `autobot-v2` running and healthy
- `/health`: healthy
- websocket: connected
- instances: 14
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

## Warnings / Limits

- Historical reports and raw research datasets were intentionally preserved. P18A did not destructively delete OHLCV snapshots because raw market-data history is audit evidence.
- OHLCV deduplication remains a dataset-builder responsibility. P17 confirmed deduplicated bars are used by historical validation runs.
- The Alpha Lab defines gates and hypotheses, but does not execute a new alpha strategy.

## Recommendation

Proceed to P18B only as a read-only alpha smoke-test runner using the new `alpha_hypotheses.json`, starting with `volatility_breakout` or `long_trend`. No capital, no live, no promotion.
