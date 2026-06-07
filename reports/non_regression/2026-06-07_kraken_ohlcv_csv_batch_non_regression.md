# Non-Regression - Kraken OHLCV CSV Batch - 2026-06-07

Verdict: `PASS_WITH_WARNINGS`

## What Changed

Code:

- `src/autobot/v2/research/batch_strategy_validation.py`
  - Added research-only support for `data_source=csv`.
  - Kept existing `autobot_state_db` behavior.
  - Added data source/path metadata to batch reports.
- `src/autobot/v2/research/validation_runner.py`
  - Fixed CSV replay to respect `start_at`, `end_at` and `limit`.
- `src/autobot/v2/cli.py`
  - Added `--data-source` and `--data-path` to `strategy-experiments-batch`.
  - Kept `--state-db` for existing state DB runs.

Tests:

- `tests/research/test_batch_strategy_validation.py`
  - Added CSV batch validation coverage.
- `tests/research/test_validation_runner.py`
  - Added CSV temporal filtering coverage.
- `tests/test_v2_cli.py`
  - Added CLI CSV batch coverage.

Reports/data:

- `reports/research/data_quality_kraken_ohlcv_2026_06_07/`
- `reports/research/kraken_ohlcv_batch_5m_2026_06_07/`
- `reports/research/kraken_ohlcv_batch_5m_walk_forward_2026_06_07/`
- `reports/research/kraken_ohlcv_foundation_batch_2026-06-07.md`

## What Must Not Have Changed

Confirmed:

- No live trading flag was enabled.
- No `PAPER_TRADING` behavior was changed to allow real trading.
- No `LIVE_TRADING_CONFIRMATION` behavior was changed.
- No Kraken order path was modified.
- No runtime paper/live service was started.
- No VPS restart was performed.
- No strategy was promoted.
- No sizing, leverage, risk or execution runtime parameter was increased.
- No strategy registry mutation was performed.
- Instance duplication remains blocked by existing feature-flag and policy work.

## Commands Run

Collection:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id kraken_ohlcv_foundation_2026_06 --symbols TRXEUR,XXLMZEUR,XXBTZEUR,XETHZEUR --timeframes 1m,5m,15m,1h --max-pages 3 --sleep-seconds 0.35 --output-dir data/research/kraken_ohlcv_foundation_2026_06
```

Data quality:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli data-quality --run-id kraken_ohlcv_quality_2026_06_07 --paths <16 parquet files> --output-dir reports/research/data_quality_kraken_ohlcv_2026_06_07
```

Backtest batch:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli strategy-experiments-batch --run-id kraken_ohlcv_batch_5m_2026_06_07 --data-source csv --data-path data/research/kraken_ohlcv_foundation_2026_06/kraken_ohlcv_foundation_2026_06_combined_5m.csv --symbols TRXEUR,XLMZEUR,BTCZEUR,ETHZEUR --strategies grid,trend,mean_reversion --timeframe 5m --output-dir reports/research/kraken_ohlcv_batch_5m_2026_06_07 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Walk-forward batch:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli strategy-experiments-batch --run-id kraken_ohlcv_batch_5m_walk_forward_2026_06_07 --data-source csv --data-path data/research/kraken_ohlcv_foundation_2026_06/kraken_ohlcv_foundation_2026_06_combined_5m.csv --symbols TRXEUR,XLMZEUR,BTCZEUR,ETHZEUR --strategies grid,trend,mean_reversion --timeframe 5m --mode walk_forward --output-dir reports/research/kraken_ohlcv_batch_5m_walk_forward_2026_06_07 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Validation:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py tests\test_instance_split_policy.py tests\test_instance_split_planner.py -q
```

Result:

- `compileall`: PASS.
- Focused pytest: `141 passed in 1.85s`.

## Evidence

Data quality:

- Overall status: `ready_for_research`.
- Usable files: `16`.
- Unusable files: `0`.
- Data gaps: `0`.
- Bid/ask: absent.
- Order-book depth: absent.
- Duplicate bars: present at page boundaries.

Backtest batch:

- Full window net PnL: `-96.582307 EUR`.
- Full window trades: `171`.
- Profitable cells: `0`.
- Strategy statuses:
  - `grid`: `research_only`
  - `trend`: `research_only`
  - `mean_reversion`: `research_only`

Walk-forward:

- Full window net PnL: `-53.533812 EUR`.
- Full window trades: `98`.
- Early/middle/late subwindows had insufficient walk-forward folds.
- No strategy passed promotion criteria.

## Warnings

- Public Kraken OHLCV does not include bid/ask or order-book depth. It is better
  than runtime price samples but still incomplete for scalping-grade cost
  realism.
- The sampled public OHLCV window is still short: around 2 days at 5m and around
  30 days at 1h. It is not enough for final strategy acceptance.
- The generated OHLCV data lives under `data/research/`, which is normally a
  local research artifact area. Reports are committed; large raw datasets should
  remain managed deliberately.

## Live Safety Confirmation

- No live order was created.
- No Kraken private endpoint was called during collection.
- No API key was read or exposed.
- No strategy registry mutation happened.
- No runtime service was restarted.
- No live/paper execution module was changed.
- No feature was added that can affect runtime entries, exits, sizing or risk.

## Recommendation

Safe to continue research measurement work.

Next recommended run:

1. Extend public OHLCV collection to a larger sample.
2. Add or collect bid/ask/depth snapshots separately.
3. Re-run CSV batch validation on a longer dataset.
4. Keep all strategies `research_only` until results survive costs, larger
   samples, walk-forward and paper parity.
