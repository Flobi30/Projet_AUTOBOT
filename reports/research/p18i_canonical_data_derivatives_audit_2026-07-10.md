# P18I Canonical Data + Derivatives Source Audit - 2026-07-10

Generated: `2026-07-10`

## Verdict

`PASS_WITH_WARNINGS`

P18I adds a research-only canonical OHLCV foundation and derivative-data readiness audit. No trading runtime, router, executor, sizing, leverage, UI, paper capital, shadow activation, promotion, or order path was changed.

Main warning: the canonical OHLCV snapshot is cleanly deduplicated, but still has many gaps and only covers a short historical period. It is suitable as a reproducible research input, not as enough evidence to retest already rejected OHLCV strategies by itself.

## Files Changed

- `src/autobot/v2/research/canonical_ohlcv_store.py`
- `src/autobot/v2/research/data_capability_scanner.py`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_canonical_ohlcv_store.py`
- `tests/research/test_data_capability_scanner.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`

Generated locally:

- `data/research/manifests/p18i_canonical_ohlcv_20260710_canonical_ohlcv.json`
- `reports/research/canonical_ohlcv/p18i_canonical_ohlcv_20260710.md`
- `reports/research/canonical_ohlcv/p18i_canonical_ohlcv_20260710.json`
- `reports/research/p18i_pre_scan/p18i_pre_canonical_scan_20260710.md`
- `reports/research/p18i_post_scan/p18i_post_canonical_scan_20260710.md`

The canonical CSV snapshot itself is generated data and should remain on the machine/VPS data volume, not become source code.

## Canonical OHLCV Store

New CLI:

```bash
python -m autobot.v2.cli canonicalize-ohlcv \
  --run-id p18i_canonical_ohlcv_20260710 \
  --raw-paths data/research \
  --output-dir data/research/canonical/ohlcv \
  --manifest-dir data/research/manifests \
  --quarantine-dir data/research/quarantine \
  --report-dir reports/research/canonical_ohlcv
```

Canonical key:

```text
exchange + market_type + symbol + timeframe + open_timestamp
```

Behavior:

- reads existing raw OHLCV CSV files;
- normalizes symbols and timeframes;
- normalizes timestamps to UTC;
- deduplicates deterministically;
- sorts chronologically;
- detects gaps;
- preserves source provenance per row;
- writes a manifest and fingerprint;
- is idempotent for identical inputs;
- never imports or calls runtime order paths.

## OHLCV Before / After

Pre-canonical data capability scan:

- spot OHLCV rows detected: `236407`
- duplicate count detected: `126304`
- period: `2026-05-08T13:00:00+00:00` -> `2026-06-16T14:50:00+00:00`
- canonical_ohlcv_ready: `False`

Canonical snapshot:

- snapshot_id: `ohlcv_cc74a0fe4f8170c1`
- fingerprint: `cc74a0fe4f8170c1f0b0ffc89f0b97eb9e847ee440e3ce38223054d496c24fbd`
- raw files: `60`
- raw rows: `362711`
- canonical rows: `166149`
- duplicates removed: `196562`
- final duplicate count: `0`
- gaps detected: `22799`
- quarantined rows: `0`
- canonical storage size: `34879551` bytes
- period: `2026-05-08T13:00:00+00:00` -> `2026-06-16T14:50:00+00:00`
- symbols: `AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR`
- timeframes: `15m, 1h, 1m, 5m`

Post-canonical data capability scan:

- spot_ohlcv quality: `canonical_ready_with_gaps`
- multi_symbol_ohlcv quality: `ready_for_cross_sectional_research`
- duplicate_count: `0`
- funding_data_ready: `False`
- basis_data_ready: `False`
- open_interest_ready: `False`
- liquidation_data_ready: `False`

## Data Versioning

Each canonical snapshot receives:

- `snapshot_id`
- `fingerprint`
- `new_data_significance`

Rejected hypotheses are not automatically re-run. Retest requires one of:

- significant new canonical data period;
- genuinely new thesis;
- genuinely different template;
- new relevant data family.

Minor additions or identical fingerprints keep rejected OHLCV templates blocked.

## Scheduler State

The scheduler/data scanner now exposes:

- `canonical_ohlcv_ready`
- `snapshot_id`
- `new_data_significance`
- `funding_data_ready`
- `basis_data_ready`
- `open_interest_ready`
- `liquidation_data_ready`
- `hypotheses_unlocked`
- `hypotheses_still_blocked`

Current unlocked by data availability only:

- `cross_sectional_momentum`
- `long_trend`
- `order_flow_imbalance`
- `relative_value`
- `volatility_breakout`

Current blocked:

- `funding_basis`: missing funding rates and spot/perp basis
- `liquidation_cascade`: missing liquidation events
- `news_event_filter`: missing news/sentiment

Already rejected OHLCV templates remain blocked unless the retest gate sees significant new data or a truly distinct template.

## Backfill Plan

No massive backfill was launched in P18I.

Official Kraken Spot OHLC currently returns only a bounded recent window, so a 6-12 month spot OHLCV target needs either progressive local accumulation, a verified external public CSV source, or a CCXT/public-provider route that is validated before use.

Bounded plan:

1. Priority symbols: `BTCZEUR, ETHZEUR, SOLEUR, XRPZEUR, ADAEUR, LINKEUR`.
2. Timeframes: `5m, 15m, 1h`.
3. Target: 6 months minimum, 12 months preferred if source supports it cleanly.
4. Batch only, never tick runtime.
5. Resume manifest required.
6. Run canonicalization after every raw collection.
7. Retest rejected OHLCV hypotheses only if snapshot significance is `significant_new_period`.

Storage estimate from current data:

- current canonical snapshot: ~33.3 MiB;
- 12-month equivalent with same symbol/timeframe density: roughly 9.3x current storage before compression;
- recommendation: keep raw immutable, canonical deduped, and consider compressed CSV/Parquet later if storage grows.

## Derivatives Source Audit

Repo modules already present:

- `src/autobot/v2/modules/funding_rates.py`
- `src/autobot/v2/modules/open_interest.py`
- `src/autobot/v2/modules/liquidation_heatmap.py`

These are not enough to unlock `funding_basis` or `liquidation_cascade` because P18I did not find a validated historical collector/feed with manifests, symbol mapping, gaps, and canonical storage.

Official sources checked:

- Kraken Spot OHLC official docs: public OHLC returns recent OHLC data and is bounded. Source: https://docs.kraken.com/api-reference/market-data/get-ohlc-data
- Kraken Futures historical funding official docs: public historical funding endpoint exists. Source: https://docs.kraken.com/api-reference/historical-funding-rates/historical-funding-rates
- Kraken Futures tickers/instruments official docs: useful candidates for current futures market data, contract metadata, and basis mapping, but historical basis/OI support still needs a focused P18J verification before ingestion. Sources: https://docs.kraken.com/api-reference/market-data/get-ticker-by-symbol and https://docs.kraken.com/api-reference/instrument-details/get-instruments
- CCXT docs: unified derivatives methods exist for some exchanges, including funding/open-interest methods, but exchange support must be verified per venue before relying on it. Source: https://docs.ccxt.com/

Capability ranking for future integration:

1. `funding + perp/index/basis`
   - Highest research value for `funding_basis`.
   - Kraken Futures funding endpoint is official and public.
   - Needs symbol mapping from AUTOBOT spot pairs to futures/perp contracts.
   - Needs canonical derivative-data schema.

2. `open_interest`
   - Useful context for funding/basis and liquidation hypotheses.
   - Medium complexity.
   - Must be real OI, not inferred from OHLCV.

3. `liquidations`
   - Useful for `liquidation_cascade`.
   - Higher complexity and provider risk.
   - No reliable Kraken public liquidation-event feed was integrated in P18I.

4. `news/sentiment`
   - Lowest priority for now.
   - More ambiguous signal quality and higher data-cleaning burden.

P18J recommendation:

Build a disabled-by-default, research-only Kraken Futures public collector prototype for:

- historical funding rates;
- futures instruments/tickers metadata;
- mark/index/perp price or basis if the official endpoint coverage is confirmed.

Do not mark `funding_basis` runnable until funding plus perp/index or basis data are actually collected, canonicalized, and validated.

## Runtime Isolation

The P18I collectors/scanners are batch research tools.

They do not:

- run per tick;
- call router/runtime executor;
- create orders;
- promote hypotheses;
- enable paper capital;
- enable live;
- change sizing/leverage;
- touch UI.

## Tests

Executed locally:

```bash
$env:PYTHONPATH='src'; python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py -q
```

Result:

- `24 passed`
- `68 passed`
- `123 passed`

Coverage added:

- deterministic deduplication;
- idempotent fingerprint/snapshot;
- UTC timestamp normalization;
- gap detection;
- symbol mapping normalization;
- identical fingerprint on identical data;
- significant vs minor data additions;
- funding remains DATA_MISSING without real funding data;
- liquidation remains DATA_MISSING without real liquidation data;
- scheduler exposes canonical/snapshot readiness;
- CLI registration for canonicalization.

## VPS Deployment Check

Code deployment commit:

- `01d581ebdb17fc1790ab135fb12954e63c6ecd51`

VPS/container checks after rebuild:

- container: `autobot-v2`
- status: `healthy`
- `/health`: `healthy`
- websocket: `connected`
- instances: `14`
- container compileall: `OK`
- recent critical log scan: no critical error, traceback, live order, or Kraken order line detected.

Flags:

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR=unset`

VPS canonical snapshot from existing daily OHLCV:

- snapshot_id: `ohlcv_fc3636d545006ce8`
- fingerprint: `fc3636d545006ce8de8a0a78a77408e2536223397f2d7912b0e12133914c619c`
- raw files: `1141`
- raw rows: `822661`
- canonical rows: `165494`
- duplicates removed: `657167`
- final duplicate count: `0`
- gaps detected: `0`
- quarantine: `0`
- storage size: `38169111` bytes
- period: `2026-05-16T16:00:00+00:00` -> `2026-07-10T00:15:00+00:00`
- symbols: `AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR`
- timeframes: `15m, 1h, 5m`

VPS post-scan:

- `canonical_ohlcv_ready=True`
- `snapshot_id=ohlcv_fc3636d545006ce8`
- `new_data_significance=same_data`
- `funding_data_ready=False`
- `basis_data_ready=False`
- `open_interest_ready=False`
- `liquidation_data_ready=False`
- still blocked: `funding_basis, liquidation_cascade, news_event_filter`
- unlocked by data availability only: `cross_sectional_momentum, long_trend, order_flow_imbalance, relative_value, volatility_breakout`

## Safety

- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- no order path called
- no runtime trading touched
- no UI touched
- grid remains no-go

## Verdict

`PASS_WITH_WARNINGS`

AUTOBOT now has a reproducible canonical OHLCV foundation and explicit derivative-data blockers. The next useful step is P18J: implement a small disabled-by-default research collector for the highest-ranked derivative capability only after confirming the official Kraken Futures data shape.
