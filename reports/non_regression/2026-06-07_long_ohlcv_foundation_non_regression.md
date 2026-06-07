# Non-Regression - Long OHLCV Foundation - 2026-06-07

Verdict: PASS_WITH_WARNINGS

## Scope

Research-only changes after `c736bc0`.

Modified or added:

- `src/autobot/v2/research/historical_data_collector.py`
- `src/autobot/v2/research/data_quality_report.py`
- `src/autobot/v2/research/spread_depth_recorder.py`
- `src/autobot/v2/research/batch_strategy_validation.py`
- `src/autobot/v2/cli.py`
- `docs/DATA_PROVIDER_STRATEGY.md`
- `tests/research/test_historical_data_collector_long_range.py`
- `tests/research/test_data_quality_status_tiers.py`
- `tests/research/test_batch_strategy_decision_thresholds.py`
- `tests/research/test_spread_depth_recorder.py`
- `tests/research/test_data_quality_report.py`
- `reports/research/kraken_ohlcv_long_history_plan_2026-06-07.md`
- `reports/research/data_foundation_readiness_2026-06-07.md`
- `reports/research/bid_ask_depth_capture_plan_2026-06-07.md`
- `reports/research/research_paper_parity_next_steps_2026-06-07.md`

Generated validation artifacts:

- `data/research/historical_long_foundation_smoke_2026_06_07/` (local smoke dataset, ignored by git if data rules apply)
- `reports/research/batch_strategy_validation_2026_06_07_smoke/`

## What Changed

### Historical Collector

- Added `--start-at` and `--end-at`.
- Added forward pagination from `start_at`.
- Added strict filtering to requested time window.
- Added manifest metadata:
  - requested start/end;
  - last cursor;
  - pages fetched;
  - raw row count;
  - deduped row count;
  - duplicate count;
  - warnings.
- Added strict dedupe by `symbol + timeframe + timestamp`.
- Added `--dedupe true|false`, default true.
- Added `--fail-on-gaps`.
- Preserved public Kraken-only behavior.

### Data Quality

- Added coverage days.
- Added zero-volume ratio.
- Added bid/ask coverage.
- Added depth coverage.
- Added final usability tier.
- New tiers:
  - `ready_for_ohlcv_research`
  - `not_ready_for_cost_sensitive_intraday`
  - `ready_for_batch_validation`
  - `ready_for_paper_candidate_review`

### Microstructure

- Added `spread_depth_recorder.py`, research-only.
- Uses public Kraken depth payloads only.
- Captures best bid/ask, spread bps, top depth, latency estimate.
- Not connected to runtime trading.

### Batch Strategy Decisions

- Added `StrategyBatchDecision`.
- Strategy status now requires more evidence than positive cells:
  - net PnL;
  - profit factor;
  - drawdown;
  - window stability;
  - non-dominance by one symbol;
  - baseline evidence;
  - MFE/Cost;
  - exit capture.
- Since batch cells do not yet carry baseline/MFE/exit-capture fields, these are explicit blockers.
- No strategy was promoted.

## What Did Not Change

- No live trading flag changed.
- No `PAPER_TRADING` or `LIVE_TRADING_CONFIRMATION` behavior changed.
- No Kraken private endpoint or API key was used.
- No Kraken order was created.
- No VPS restart.
- No Docker change.
- No paper/live runtime sizing change.
- No risk manager runtime change.
- No instance duplication activation.
- No strategy promotion.

## Tests

Command:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\research tests\test_v2_cli.py -q
```

Result:

```text
144 passed in 1.96s
```

Command:

```powershell
python -m compileall -q src
```

Result: PASS

Earlier targeted command:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\research\test_historical_data_collector.py tests\research\test_historical_data_collector_long_range.py tests\research\test_data_quality_report.py tests\research\test_data_quality_status_tiers.py tests\research\test_batch_strategy_validation.py tests\research\test_batch_strategy_decision_thresholds.py tests\research\test_spread_depth_recorder.py -q
```

Result:

```text
17 passed in 0.36s
```

## Smoke Data Collection

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id 2026_06_07_kraken_smoke --symbols TRXEUR --timeframes 5m --output-dir data\research\historical_long_foundation_smoke_2026_06_07 --max-pages 1 --dedupe true --no-parquet
```

Result:

- Rows: `721`
- Start: `2026-06-05T03:55:00+00:00`
- End: `2026-06-07T15:55:00+00:00`
- Coverage: `2.5` days
- Raw duplicates: `0`
- Final duplicates: `0`
- Gaps: `0`
- Zero-volume ratio: `0.0139`
- Bid/ask coverage: `0.0`
- Depth coverage: `0.0`
- Tier: `not_ready_for_cost_sensitive_intraday`

## Batch Smoke

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli strategy-experiments-batch --run-id 2026_06_07_batch_smoke_trx_5m --data-source csv --data-path data\research\historical_long_foundation_smoke_2026_06_07\2026_06_07_kraken_smoke_TRXEUR_5m.csv --symbols TRXEUR --strategies grid,trend,mean_reversion --timeframe 5m --mode backtest --output-dir reports\research\batch_strategy_validation_2026_06_07_smoke --min-closed-trades 30 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Result:

- `grid`: `research_only`
- `trend`: `research_only`
- `mean_reversion`: `research_only`
- No validation window net positive after costs.
- No strategy promoted.
- Main blockers:
  - insufficient sample;
  - non-positive aggregate PnL;
  - missing baseline evidence;
  - missing MFE/Cost;
  - missing exit capture;
  - no stable multi-window support.

## Warnings / Limits

- `PASS_WITH_WARNINGS` because Kraken REST OHLC smoke coverage is only 2.5 days for 5m.
- Bid/ask/depth are still absent from OHLCV and must be captured separately.
- The batch runner now intentionally blocks shadow candidacy until baseline/MFE/exit-capture fields are available.
- The long-history target still depends on accumulating local data or adding a public historical source beyond the bounded Kraken REST OHLC window.

## Live Safety Confirmation

- Live remains blocked.
- No live code path was modified.
- No order executor was modified.
- No risk manager runtime was modified.
- No paper runtime executor was modified.
- No strategy registry mutation was performed.
- No instance split executor was activated.

## Recommendation

Proceed to the next step only after collecting longer OHLCV and public spread/depth snapshots. The next exact run should be a Priority 1 OHLCV bootstrap followed by data quality:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id kraken_p1_bootstrap_5m_2026_06_07 --symbols BTCZEUR,ETHZEUR,XLMZEUR,TRXEUR --timeframes 5m --output-dir data/research/kraken_p1_bootstrap --max-pages 5 --dedupe true --no-parquet
python -m autobot.v2.cli data-quality --run-id kraken_p1_bootstrap_quality_2026_06_07 --paths <comma-separated-csv-files> --default-timeframe 5m --output-dir reports/research/data_foundation/kraken_p1_bootstrap
```
