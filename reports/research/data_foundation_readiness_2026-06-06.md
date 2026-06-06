# Data Foundation Readiness - 2026-06-06

Generated evidence: `reports/research/data_foundation_2026-06-06/data_foundation_readiness_2026-06-06.md`

## Verdict

Status: `not_ready` for final strategy validation.

The current CSV datasets built from runtime `market_price_samples` are useful for diagnostics and smoke replay, but not strong enough to conclude that a strategy is viable.

## Evidence

| Dataset | Rows | Period | Symbols | Gaps | Volume | Bid/Ask | Depth | Usable |
| --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| 1m canonical smoke | 80920 | 2026-05-28 to 2026-06-04 | 14 | 18129 | absent/zero | absent | absent | no |
| 5m canonical smoke | 24003 | 2026-05-28 to 2026-06-04 | 14 | 23989 | absent/zero | absent | absent | no |
| 15m canonical smoke | 9089 | 2026-05-28 to 2026-06-04 | 14 | 9075 | absent/zero | absent | absent | no |

## Added Data Foundation

- `src/autobot/v2/research/historical_data_collector.py`: public Kraken REST OHLCV collector, research-only, no private endpoint, no orders.
- `src/autobot/v2/research/data_quality_report.py`: detects gaps, duplicates, missing volume, missing bid/ask, missing depth and coverage.
- `docs/DATA_PROVIDER_STRATEGY.md`: data-provider strategy and why Databento is not first priority for Kraken spot crypto.
- CLI:
  - `python -m autobot.v2.cli collect-history ...`
  - `python -m autobot.v2.cli data-quality ...`

## Why Databento Is Not Priority Now

AUTOBOT trades Kraken spot crypto. The immediate gap is not a premium vendor; it is clean Kraken-compatible OHLCV plus bid/ask/depth capture. Public Kraken OHLCV or CCXT can provide first historical coverage. Databento can be revisited later for deeper market microstructure, but it is not the shortest path to fixing research/paper parity.

## Next Data Work

1. Collect Kraken OHLCV for at least several months for 1m, 5m, 15m and 1h.
2. Add bid/ask/depth snapshots if strategies remain cost-sensitive intraday.
3. Mark runtime sample datasets as diagnostic-only unless gaps are repaired and volume/book data are provided.
4. Do not promote strategies from `market_price_samples` alone.
