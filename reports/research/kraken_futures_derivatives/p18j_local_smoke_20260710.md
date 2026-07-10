# Kraken Futures Derivatives Collection - p18j_local_smoke_20260710

Generated at: `2026-07-10T02:52:37.437095+00:00`
Snapshot: `kraken_futures_d328051f99fe0cde`
Fingerprint: `d328051f99fe0cde460a885bf13f14b583768e259dab8f177d4ae12bdd48b537`

## Mappings

| Futures Symbol | Base | Quote | AUTOBOT Spot Symbol | Pair |
| --- | --- | --- | --- | --- |
| `PF_XBTUSD` | `BTC` | `USD` | `BTCZEUR` | `BTC:USD` |
| `PF_ETHUSD` | `ETH` | `USD` | `ETHZEUR` | `ETH:USD` |

## Datasets

| Dataset | Rows | Duplicates | Invalid | Start | End | Quality | Path |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| `funding_rates` | 17874 | 0 | 0 | 2025-07-02T08:00:00+00:00 | 2026-07-10T02:00:00+00:00 | `historical_funding_ready` | `data\research\canonical\derivatives\funding\p18j_local_smoke_20260710_funding_rates.csv` |
| `ticker_snapshots` | 2 | 0 | 0 | 2026-07-10T02:52:35+00:00 | 2026-07-10T02:52:35+00:00 | `current_snapshot_ready` | `data\research\canonical\derivatives\tickers\p18j_local_smoke_20260710_ticker_snapshots.csv` |
| `derivatives_candles` | 30 | 0 | 0 | 2026-07-10T02:48:00+00:00 | 2026-07-10T02:52:00+00:00 | `bounded_candle_sample_ready` | `data\research\canonical\derivatives\candles\p18j_local_smoke_20260710_derivatives_candles.csv` |
| `basis` | 2 | 0 | 0 | 2026-07-10T02:52:35+00:00 | 2026-07-10T02:52:35+00:00 | `current_basis_same_quote_ready` | `data\research\canonical\derivatives\basis\p18j_local_smoke_20260710_basis.csv` |

## Readiness

- funding_history_ready: `True`
- funding_history_start: `2025-07-02T08:00:00+00:00`
- funding_history_end: `2026-07-10T02:00:00+00:00`
- mark_candles_ready: `True`
- trade_candles_ready: `True`
- spot_reference_candles_ready: `True`
- current_open_interest_ready: `True`
- open_interest_history_ready: `False`
- predicted_funding_ready: `True`
- basis_current_ready: `True`
- basis_history_ready: `False`
- basis_confidence_status: `MARK_INDEX_SAME_QUOTE`
- derivatives_data_quality: `smoke_ready_current_basis_only`
- errors: `0`
- raw_response_count: `10`

## Safety

- Research-only Kraken Futures public market-data collection.
- No private endpoint, order endpoint, API key, paper capital, live trading, promotion, shadow activation, sizing, leverage, UI, or runtime order path.
- Raw official responses are preserved for audit.
- paper_capital_allowed: `False`
- live_allowed: `False`
- promotable: `False`
