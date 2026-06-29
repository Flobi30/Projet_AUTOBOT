# Strategy Edge Daily Runner Integration Non-Regression - 2026-06-29

Verdict: PASS

## Scope

Integrate the research-only strategy edge review into the daily research data
collection runner.

This change does not touch the official paper/live trading runtime. It only
adds a report step after:

1. High Conviction walk-forward report generation;
2. Strategy Orchestrator report generation.

## Files Modified

- `config/research_data_collection.yaml`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `tests/research/test_daily_data_collection_runner.py`

## Logic Modified

- Added `strategy_edge_review` config block.
- Added `DailyStrategyEdgeReviewConfig`.
- Added `strategy_edge_review_report_path` to daily collection results.
- Added `_run_strategy_edge_review()` after High Conviction and Strategy Orchestrator.
- Added a safe `skipped` state when prerequisite reports are missing.
- Added report links to the daily collection markdown.

## What Did Not Change

- No live trading flag was changed.
- No official paper trading route was changed.
- No strategy router runtime behavior was changed.
- No sizing or risk runtime behavior was changed.
- No Kraken order path was changed.
- No instance split/child creation was enabled.

## Tests Run

```text
python -m compileall -q src
```

Result: PASS

```text
$env:PYTHONPATH='src'; python -m pytest tests/research/test_daily_data_collection_runner.py tests/research/test_strategy_edge_improvement.py -q
```

Result: 8 passed

```text
$env:PYTHONPATH='src'; python -m pytest tests/test_v2_cli.py::test_cli_collect_research_daily_is_research_only tests/test_v2_cli.py::test_cli_strategy_edge_review_writes_research_only_reports -q
```

Result: 2 passed

```text
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q
```

Result: 229 passed

## Safety Confirmation

- research_only: true
- orders_created: false
- official_paper_modified: false
- live_modified: false
- runtime_router_modified: false
- runtime_sizing_modified: false
- child_instance_created: false
- live_promotion_allowed: false

## Deployment Notes

The service image must be rebuilt for the daily Docker runner to see the new
code because `/app/src` is not mounted as a host volume.

Planned deployment:

```text
git pull/fast-forward on VPS
docker compose build autobot
docker compose up -d autobot
```

Post-deploy checks required:

- `/health`
- container status
- websocket connected
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- no recent critical logs
- no live order submission

