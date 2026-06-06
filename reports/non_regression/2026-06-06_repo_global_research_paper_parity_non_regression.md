# Non-Regression - Repo Global Research/Paper Parity - 2026-06-06

Verdict: PASS_WITH_WARNINGS

Commit base: `8f06680`

## What Changed

Files added:

- `src/autobot/v2/research/historical_data_collector.py`
- `src/autobot/v2/research/data_quality_report.py`
- `src/autobot/v2/research/batch_strategy_validation.py`
- `src/autobot/v2/research/research_paper_parity.py`
- `src/autobot/v2/instance_split_policy.py`
- `src/autobot/v2/instance_split_planner.py`
- `docs/DATA_PROVIDER_STRATEGY.md`
- research reports under `reports/research/`
- tests for data foundation, parity and split policy/planner

Files modified:

- `src/autobot/v2/cli.py`: new research-only commands:
  - `collect-history`
  - `data-quality`
  - `strategy-experiments-batch`
  - `research-paper-parity`
  - `split-plan`
- `src/autobot/v2/research/data_quality_report.py`: recognizes `depth_eur`; datasets with gaps are marked unusable for backtest conclusions.
- `tests/test_v2_cli.py`: CLI coverage for `data-quality` and `split-plan`.

Endpoints/routes touched: none in runtime API/dashboard.

Modules critical impacted: research CLI only, research data-quality, read-only split planner. No runtime execution module was changed.

## What Must Not Have Changed

| Area | Status |
| --- | --- |
| Dashboard | not modified |
| Paper trading executor | not modified |
| Live safety env | not modified |
| Strategy router runtime | not modified |
| Risk manager runtime | not modified |
| Existing API routes | not modified |
| Docker/VPS behavior | not modified |
| Persistent runtime DB | read-only only |
| Order sizing/leverage | not modified |
| Kraken API keys | not touched |

## Trading Safety

- No strategy was promoted.
- `grid`, `trend`, and `mean_reversion` remain `research_only` in the new batch report.
- No live trading flag was changed.
- No `PAPER_TRADING` behavior was changed to allow real orders.
- `LIVE_TRADING_CONFIRMATION` was not modified.
- No Kraken live order was created.
- `InstanceSplitPolicy` always reports `live_promotion_allowed=false`.
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` defaults to false.
- New split planner is read-only and creates no child instance.

## Tests

Commands executed:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py tests\test_instance_split_policy.py tests\test_instance_split_planner.py -q
```

Results:

- `compileall`: PASS.
- pytest: `138 passed in 1.79s`.

Earlier note:

- Running pytest without `PYTHONPATH=src` fails during import with `ModuleNotFoundError: No module named 'autobot'`. The project currently needs `PYTHONPATH=src` for this local test command.

## Runtime VPS Check

No VPS restart was performed.

Commands:

```powershell
Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri 'http://204.168.251.201:8080/health'
Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri 'http://204.168.251.201:8080/api/status'
Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri 'http://204.168.251.201:8080/api/runtime/trace'
```

Results:

- `/health`: PASS
  - status `healthy`
  - orchestrator `running`
  - websocket `connected`
  - instances `14`
  - uptime seconds `736844.562585`
- `/api/status`: 401 Unauthorized without auth.
- `/api/runtime/trace`: 401 Unauthorized without auth.

The 401 responses are not a runtime crash; they mean authenticated API checks were not performed in this pass.

## Evidence Reports

- `reports/research/autobot_repo_global_audit_2026-06-06.md`
- `reports/research/research_paper_cost_parity_2026-06-06.md`
- `reports/research/data_foundation_readiness_2026-06-06.md`
- `reports/research/batch_strategy_validation_2026-06-06.md`
- `reports/research/research_paper_parity_2026-06-06.md`
- `reports/research/runtime_decision_influence_2026-06-06.md`
- `reports/research/spinoff_duplication_safety_2026-06-06.md`

## Warnings

1. Data foundation is not ready: runtime-sample CSVs have gaps, zero volume, no bid/ask and no depth.
2. Research/paper parity is weak: 18 of 19 comparison buckets diverged.
3. Paper ledger contains many `realized_pnl_missing` warnings and slippage anomalies.
4. Official runtime still appears grid-dominant and is not yet proven to go through research validation/governance for every execution path.
5. Old runtime spin-off logic still needs to be wired through the new `InstanceSplitPolicy` before any split executor can be trusted.

## Can We Continue?

Yes, but only toward measurement and parity work.

Do not:

- enable live;
- promote strategies;
- enable split executor;
- increase sizing;
- lower costs;
- make grid more aggressive.

Recommended next run:

```powershell
$env:PYTHONPATH='src'; python -m autobot.v2.cli collect-history --run-id kraken_ohlcv_foundation_2026_06 --symbols TRXEUR,XLMZEUR,XXBTZEUR,XETHZEUR --timeframes 1m,5m,15m,1h --max-pages 3 --output-dir data/research/kraken_ohlcv_foundation_2026_06
```

Then:

```powershell
$env:PYTHONPATH='src'; python -m autobot.v2.cli data-quality --run-id kraken_ohlcv_foundation_quality_2026_06 --paths <generated_csvs> --default-timeframe 5m --output-dir reports/research/data_foundation_kraken_2026_06
```
