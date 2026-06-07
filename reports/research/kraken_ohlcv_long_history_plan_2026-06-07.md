# Kraken OHLCV Long History Plan - 2026-06-07

## Objective

Build a longer, reproducible OHLCV foundation before drawing strategy conclusions. This is research-only and does not touch paper/live runtime, sizing, risk, Kraken private keys, or instance duplication.

## Current Constraint

Kraken public REST OHLC is useful for bootstrapping, but it is not a full historical archive. The official Kraken OHLC documentation states that the endpoint returns a bounded recent window of OHLC entries. Practical smoke result on `2026-06-07`:

- Symbol/timeframe: `TRXEUR 5m`
- Rows: `721`
- Covered period: `2026-06-05T03:55:00+00:00` to `2026-06-07T15:55:00+00:00`
- Coverage: `2.5` days
- Final duplicates: `0`
- Gaps: `0`
- Tier: `not_ready_for_cost_sensitive_intraday`

Reference: [Kraken REST OHLC data](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data)

## Priority Universe

Priority 1:

- `BTCZEUR`
- `ETHZEUR`
- `XLMZEUR`
- `TRXEUR`

Priority 2:

- `ADAEUR`
- `AVAXEUR`
- `SOLEUR`
- `DOTEUR`
- `LINKEUR`
- `XRPEUR` if supported cleanly by Kraken symbol mapping.

## Target Timeframes

- `5m`: target `90` days
- `15m`: target `180` days
- `1h`: target `365` days

## Exact Commands

Bootstrap latest public Kraken OHLCV:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id kraken_p1_bootstrap_5m_2026_06_07 --symbols BTCZEUR,ETHZEUR,XLMZEUR,TRXEUR --timeframes 5m --output-dir data/research/kraken_p1_bootstrap --max-pages 5 --dedupe true --no-parquet
python -m autobot.v2.cli collect-history --run-id kraken_p1_bootstrap_15m_2026_06_07 --symbols BTCZEUR,ETHZEUR,XLMZEUR,TRXEUR --timeframes 15m --output-dir data/research/kraken_p1_bootstrap --max-pages 5 --dedupe true --no-parquet
python -m autobot.v2.cli collect-history --run-id kraken_p1_bootstrap_1h_2026_06_07 --symbols BTCZEUR,ETHZEUR,XLMZEUR,TRXEUR --timeframes 1h --output-dir data/research/kraken_p1_bootstrap --max-pages 5 --dedupe true --no-parquet
```

Strict gap-check run after files exist:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli data-quality --run-id kraken_p1_bootstrap_quality_2026_06_07 --paths <comma-separated-csv-files> --default-timeframe 5m --output-dir reports/research/data_foundation/kraken_p1_bootstrap
```

If the REST endpoint cannot provide the target depth, use one of these paths:

- keep accumulating local daily public OHLCV snapshots;
- evaluate CCXT Kraken public OHLCV only if it can extend coverage without private keys;
- import verified public CSV archives into `data/research/historical/`;
- revisit paid data only after the research question justifies it.

## Not Priority Now

Databento is not the immediate priority for Kraken spot crypto. The current blocker is reliable measurement and research/paper parity, not institutional data breadth.

## Success Criteria

- `0` final duplicate bars per symbol/timeframe.
- `0` unexpected gaps for strict batch validation.
- Explicit coverage days and row counts.
- `ready_for_batch_validation` only when the required historical length is met.
- `ready_for_paper_candidate_review` only when bid/ask/depth or a reliable spread proxy exists.
- No strategy promotion from this collection step.
