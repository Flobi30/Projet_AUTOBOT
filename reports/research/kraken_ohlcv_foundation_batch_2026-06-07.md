# Kraken OHLCV Foundation Batch - 2026-06-07

## Scope

This report summarizes the first public Kraken OHLCV research run after adding
CSV support to the batch strategy validation runner.

No live trading was enabled. No paper/live runtime service was started. No
Kraken private endpoint was called. No API key was read. No strategy was
promoted.

## Data Collection

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id kraken_ohlcv_foundation_2026_06 --symbols TRXEUR,XXLMZEUR,XXBTZEUR,XETHZEUR --timeframes 1m,5m,15m,1h --max-pages 3 --sleep-seconds 0.35 --output-dir data/research/kraken_ohlcv_foundation_2026_06
```

Notes:

- `XLMZEUR` is not accepted directly by Kraken OHLC. The official pair id is
  `XXLMZEUR`; the collector normalizes output to `XLMZEUR`.
- 16 OHLCV files were produced: 4 symbols x 4 timeframes.
- Symbols: `TRXEUR`, `XLMZEUR`, `BTCZEUR`, `ETHZEUR`.
- Timeframes: `1m`, `5m`, `15m`, `1h`.

## Data Quality

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli data-quality --run-id kraken_ohlcv_quality_2026_06_07 --paths <16 parquet files> --output-dir reports/research/data_quality_kraken_ohlcv_2026_06_07
```

Result:

- Overall status: `ready_for_research`.
- Usable files: `16`.
- Unusable files: `0`.
- Gaps: `0` in all collected files.
- Duplicate bars: `2` per file. These are expected at public Kraken page
  boundaries and must be deduped before larger production-grade datasets.
- Volume: mostly present, but some 1m/low-liquidity windows contain zero-volume
  bars.
- Bid/ask: absent.
- Order-book depth: absent.

Interpretation:

The dataset is materially better than `market_price_samples` for research
because it has real OHLCV and no gaps. It is still not sufficient for final
intraday/scalping cost conclusions because bid/ask/depth are absent.

## Batch Validation

Combined dataset:

```text
data/research/kraken_ohlcv_foundation_2026_06/kraken_ohlcv_foundation_2026_06_combined_5m.csv
```

Backtest command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli strategy-experiments-batch --run-id kraken_ohlcv_batch_5m_2026_06_07 --data-source csv --data-path data/research/kraken_ohlcv_foundation_2026_06/kraken_ohlcv_foundation_2026_06_combined_5m.csv --symbols TRXEUR,XLMZEUR,BTCZEUR,ETHZEUR --strategies grid,trend,mean_reversion --timeframe 5m --output-dir reports/research/kraken_ohlcv_batch_5m_2026_06_07 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Backtest result:

- Conclusion: `No validation window was net positive after costs; keep strategies research-only.`
- Status by strategy:
  - `grid`: `research_only`
  - `trend`: `research_only`
  - `mean_reversion`: `research_only`
- Full window:
  - Total trades: `171`
  - Total net PnL: `-96.582307 EUR`
  - Profitable cells: `0`
- Early window:
  - Total trades: `74`
  - Total net PnL: `-44.899986 EUR`
  - Profitable cells: `1`
  - Best cell: `XLMZEUR/mean_reversion`, `+0.545064 EUR`, only `6` trades,
    insufficient sample.
- Middle window:
  - Total trades: `52`
  - Total net PnL: `-32.495300 EUR`
  - Profitable cells: `0`
- Late window:
  - Total trades: `46`
  - Total net PnL: `-18.914030 EUR`
  - Profitable cells: `2`, both insufficient sample.
- Weekend window:
  - Total trades: `87`
  - Total net PnL: `-51.542888 EUR`
  - Profitable cells: `1`, insufficient sample.

Walk-forward command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli strategy-experiments-batch --run-id kraken_ohlcv_batch_5m_walk_forward_2026_06_07 --data-source csv --data-path data/research/kraken_ohlcv_foundation_2026_06/kraken_ohlcv_foundation_2026_06_combined_5m.csv --symbols TRXEUR,XLMZEUR,BTCZEUR,ETHZEUR --strategies grid,trend,mean_reversion --timeframe 5m --mode walk_forward --output-dir reports/research/kraken_ohlcv_batch_5m_walk_forward_2026_06_07 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Walk-forward result:

- Conclusion: `No validation window was net positive after costs; keep strategies research-only.`
- Full window:
  - Total trades: `98`
  - Total net PnL: `-53.533812 EUR`
- Early/middle/late:
  - Insufficient walk-forward folds on 241-243 bar subwindows.
- Weekend:
  - Total trades: `33`
  - Total net PnL: `-14.491930 EUR`
  - Some small positive cells exist, but they do not pass sample-size or fold
    stability requirements.

## Important Measurement Fix

During this run, the batch CSV path exposed a measurement bug: CSV validation
ignored `start_at` and `end_at`, so early/middle/late windows initially replayed
the full dataset. This was fixed in `validation_runner.load_bars_for_validation`
by applying temporal filters to CSV datasets.

Tests now cover:

- batch validation from CSV datasets;
- CLI batch validation with `--data-source csv`;
- CSV temporal filtering in the validation runner.

## Decision

AUTOBOT is measuring better than before because it can now:

- collect public Kraken OHLCV;
- inspect gaps, duplicates, volume, bid/ask and depth availability;
- run batch backtests directly from CSV datasets;
- run batch walk-forward from CSV datasets;
- keep all strategies research-only when evidence is weak.

AUTOBOT is not paper-validated or live-ready from this evidence.

The next technical gap is not to optimize parameters. It is to collect a larger
OHLCV history and add bid/ask or order-book snapshots so transaction-cost
modelling can be checked against real spread conditions.
