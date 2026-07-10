# P18J - Kraken Futures Derivatives Research Collector

Date: 2026-07-10  
Code commit: `bd06480`  
Mode: research-only

## Objective

P18J adds the first official derivatives data capability to AUTOBOT without enabling any trading path. The collector uses Kraken Futures public market-data endpoints to gather historical funding, current ticker/open-interest snapshots, small bounded candle samples, and same-quote mark/index basis.

No funding-basis strategy was tested. No liquidation-cascade collector was started.

## Files Changed

- `src/autobot/v2/research/kraken_futures_derivatives_collector.py`
- `src/autobot/v2/research/data_capability_scanner.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_kraken_futures_derivatives_collector.py`
- `tests/research/test_data_capability_scanner.py`
- `reports/research/kraken_futures_derivatives/p18j_local_smoke_20260710.md`
- `reports/research/p18j_post_scan/p18j_local_post_derivatives_scan_20260710.json`
- `reports/research/p18j_post_scan/p18j_local_post_derivatives_scan_20260710.md`

## Official Endpoints Used

Public Kraken Futures market-data endpoints only:

- `GET /derivatives/api/v3/instruments`
- `GET /derivatives/api/v3/tickers`
- `GET /derivatives/api/v3/historical-funding-rates`
- `GET /api/charts/v1/{tick_type}/{symbol}/{resolution}`

The collector has an explicit endpoint allowlist and rejects order/private-looking endpoints.

Forbidden by code policy:

- `createOrder`
- `cancelOrder`
- private trading endpoints
- order endpoints
- API key usage

## CLI

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli collect-kraken-futures-derivatives `
  --run-id p18j_local_smoke_20260710 `
  --assets BTC,ETH `
  --max-symbols 2 `
  --max-candles 5 `
  --raw-dir data/research/raw/kraken_futures `
  --canonical-dir data/research/canonical/derivatives `
  --manifest-dir data/research/manifests `
  --report-dir reports/research/kraken_futures_derivatives `
  --timeout-seconds 20
```

## Local Smoke Result

Run id: `p18j_local_smoke_20260710`  
Snapshot: `kraken_futures_d328051f99fe0cde`  
Fingerprint: `d328051f99fe0cde460a885bf13f14b583768e259dab8f177d4ae12bdd48b537`

Detected mappings:

| Futures Symbol | Base | Quote | AUTOBOT Spot Symbol |
| --- | --- | --- | --- |
| `PF_XBTUSD` | `BTC` | `USD` | `BTCZEUR` |
| `PF_ETHUSD` | `ETH` | `USD` | `ETHZEUR` |

Datasets:

| Dataset | Rows | Duplicates | Invalid | Start | End |
| --- | ---: | ---: | ---: | --- | --- |
| `funding_rates` | 17,874 | 0 | 0 | 2025-07-02T08:00:00+00:00 | 2026-07-10T02:00:00+00:00 |
| `ticker_snapshots` | 2 | 0 | 0 | 2026-07-10T02:52:35+00:00 | 2026-07-10T02:52:35+00:00 |
| `derivatives_candles` | 30 | 0 | 0 | 2026-07-10T02:48:00+00:00 | 2026-07-10T02:52:00+00:00 |
| `basis` | 2 | 0 | 0 | 2026-07-10T02:52:35+00:00 | 2026-07-10T02:52:35+00:00 |

Readiness:

| Field | Value |
| --- | --- |
| `funding_history_ready` | `true` |
| `mark_candles_ready` | `true` |
| `trade_candles_ready` | `true` |
| `spot_reference_candles_ready` | `true` |
| `current_open_interest_ready` | `true` |
| `open_interest_history_ready` | `false` |
| `predicted_funding_ready` | `true` |
| `basis_current_ready` | `true` |
| `basis_history_ready` | `false` |
| `basis_confidence_status` | `MARK_INDEX_SAME_QUOTE` |
| `derivatives_data_quality` | `smoke_ready_current_basis_only` |

## Basis Correctness

Basis is calculated only when mark and reference quote currencies match:

```text
basis_bps = ((mark_price / index_price) - 1) * 10000
```

Direct USD futures versus EUR spot basis is rejected as `BASIS_REFERENCE_UNVERIFIED`. The smoke basis is valid because Kraken Futures mark and index are both USD-referenced.

## Data Capability Scanner

Post-smoke scanner result:

- `funding_history_ready=true`
- `funding_history_start=2025-07-02T08:00:00+00:00`
- `funding_history_end=2026-07-10T02:00:00+00:00`
- `mark_candles_ready=true`
- `trade_candles_ready=true`
- `current_open_interest_ready=true`
- `open_interest_history_ready=false`
- `basis_history_ready=false`
- `predicted_funding_ready=true`
- `derivatives_symbols_ready=true`

Scheduler/hypothesis impact:

| Family | Status | Blockers |
| --- | --- | --- |
| `funding_basis` | `WAITING_FOR_MORE_DATA` | `basis_history_too_short` |
| `liquidation_cascade` | `DATA_MISSING` | `liquidation_events_missing` |

Important: current open interest is explicitly not treated as historical open interest. Current basis is explicitly not treated as basis history.

## Storage Layout

New canonical datasets:

- `data/research/raw/kraken_futures/`
- `data/research/canonical/derivatives/funding/`
- `data/research/canonical/derivatives/tickers/`
- `data/research/canonical/derivatives/candles/`
- `data/research/canonical/derivatives/basis/`
- `data/research/manifests/`

Raw official responses are preserved for audit. Canonical rows are deduplicated and fingerprinted.

## Tests

Commands:

```powershell
$env:PYTHONPATH='src'
python -m compileall -q src
python -m pytest tests\research\test_kraken_futures_derivatives_collector.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q
```

Result:

- compileall: OK
- pytest: `71 passed`

Covered:

- funding parsing
- ticker parsing
- mark/index/open-interest parsing
- same-quote basis
- USD/EUR basis rejection
- deterministic dedupe/idempotence/fingerprint
- UTC timestamps
- current OI distinct from historical OI
- funding_basis blocked without basis history
- liquidation_cascade remains data-missing
- order endpoints rejected
- no paper/live/promotion

## VPS Deployment

Pending at initial report creation. This section must be updated after GitHub/VPS/container synchronization and VPS smoke execution.

## Safety

- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- no live trading
- no paper capital
- no promotion
- no shadow activation
- no order endpoint
- no private API
- no UI change
- no sizing/leverage change
- no runtime order path
- grid remains no-go

## Recommendation P18K

Do not test `funding_basis` yet. First accumulate a small but real forward history of ticker snapshots, open interest, predicted funding, premium, spread, and same-quote basis. P18K should be a bounded scheduler/service wrapper for this collector, disabled by default or explicitly research-only, with retention and disk limits.
