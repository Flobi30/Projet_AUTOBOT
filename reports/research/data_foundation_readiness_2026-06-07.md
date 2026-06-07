# Data Foundation Readiness - 2026-06-07

## Summary

AUTOBOT now distinguishes clean OHLCV research data from data that is sufficient for intraday cost-sensitive strategy validation.

New tiers:

- `ready_for_ohlcv_research`
- `not_ready_for_cost_sensitive_intraday`
- `ready_for_batch_validation`
- `ready_for_paper_candidate_review`

## Smoke Evidence

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-history --run-id 2026_06_07_kraken_smoke --symbols TRXEUR --timeframes 5m --output-dir data\research\historical_long_foundation_smoke_2026_06_07 --max-pages 1 --dedupe true --no-parquet
```

Result:

| Symbol | Timeframe | Rows | Coverage | Final Duplicates | Gaps | Zero Volume Ratio | Bid/Ask | Depth | Tier |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TRXEUR | 5m | 721 | 2.5 days | 0 | 0 | 0.0139 | 0.000 | 0.000 | not_ready_for_cost_sensitive_intraday |

Interpretation:

- The CSV is usable for basic OHLCV inspection.
- It is not sufficient to validate grid/scalping cost-sensitive execution.
- Bid/ask and depth must be collected before replacing fixed spread assumptions.
- A 2.5 day sample cannot support strategy promotion.

## Current Decision

No strategy should be promoted from this dataset. It is a smoke dataset only.

## Next Required Data

- Long OHLCV history by symbol/timeframe.
- Spread/depth snapshots by symbol.
- Research/paper cost parity once a longer dataset exists.
