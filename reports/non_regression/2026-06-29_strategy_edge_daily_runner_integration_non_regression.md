# Strategy Edge Daily Runner Integration Non-Regression - 2026-06-29

Verdict: PASS_WITH_WARNINGS

## Scope

Integrate the research-only strategy edge review into the daily research data
collection runner.

This change does not touch the official paper/live trading runtime. It only
adds a report step after:

1. High Conviction walk-forward report generation;
2. Strategy Orchestrator report generation.

## Files Modified

- `config/research_data_collection.yaml`
- `deploy/systemd/run-autobot-research-collection.sh`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `tests/research/test_daily_data_collection_runner.py`

## Logic Modified

- Added `strategy_edge_review` config block.
- Added `DailyStrategyEdgeReviewConfig`.
- Added `strategy_edge_review_report_path` to daily collection results.
- Added `_run_strategy_edge_review()` after High Conviction and Strategy Orchestrator.
- Added a safe `skipped` state when prerequisite reports are missing.
- Added report links to the daily collection markdown.
- Mounted `reports/research/strategy_edge` in the isolated systemd Docker runner.

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
code because `/app/src` is not mounted as a host volume. The systemd runner also
needs the new `reports/research/strategy_edge` bind mount so the read-only
research container can write the edge reports.

Deployment executed on the VPS:

```text
git fetch origin master
git merge --ff-only origin/master
docker compose build autobot
docker compose up -d autobot
```

Post-deploy checks:

- deployed commit: `3e2b144`
- `/health`: healthy
- orchestrator: running
- websocket: connected
- instances: 14
- container: `autobot-v2` up and healthy
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- recent critical log scan: no matching critical/live-order output

The isolated systemd daily timer is active. The next run observed after deploy
was scheduled for `2026-06-30 00:18:39 UTC` (about `02:18` Europe/Paris).

## VPS Research Smoke

A very short end-to-end research smoke was started with a temporary config
covering two symbols and one microstructure sample. It produced OHLCV,
microstructure, microstructure profile and data-readiness artifacts, but was
stopped after the command exceeded the local 5 minute observation window before
the full High Conviction / Strategy Orchestrator / Strategy Edge phase finished.
No main runtime container was restarted or modified by that smoke.

To verify the new Strategy Edge brick itself, a narrower isolated container was
run with:

```text
python -m autobot.v2.cli strategy-edge-review \
  --run-id edge_review_latest_2026_06_29T19_08_56Z \
  --output-dir /app/reports/research/strategy_edge \
  --high-conviction-report /app/reports/research/high_conviction_walk_forward/daily_2026_06_29T00_17_57Z_high_conviction_walk_forward.json \
  --strategy-orchestrator-report /app/reports/research/strategy_orchestrator/daily_2026_06_29T00_17_57Z_strategy_orchestrator.json
```

Result: PASS.

The direct strategy edge run reported:

- `live_promotion_allowed=false`
- `orders_created=false`
- `paper_candidate_allowed=false`
- High Conviction remains `active_research_keep_testing`
- Trend Momentum remains `research_signal_only`
- Mean Reversion remains `research_signal_only`
- Relative Value remains `no_go`
- Grid remains `archived`

Warning: the first full scheduled daily run after this deployment remains the
real end-to-end confirmation for the entire daily pipeline. The code path and
mounts are validated; the complete daily runtime duration should be observed on
the next timer execution.
