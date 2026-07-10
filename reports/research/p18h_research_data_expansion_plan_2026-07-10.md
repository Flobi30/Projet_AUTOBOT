# P18H Research Data Expansion Plan - p18h_research_data_expansion_plan_2026-07-10

Generated at: `2026-07-10T01:07:21.962442+00:00`

## Data Capabilities

| Capability | Available | Rows | Symbols | Timeframes | Start | End | Quality | Unlocks | Blockers |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| `spot_ohlcv` | `True` | 236407 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XBTZEUR, XETHZEUR, XLMZEUR, XLTCZEUR, XRPZEUR, XXBTZEUR, XXLMZEUR, XXRPZEUR | 15m, 1h, 1m, 5m | 2026-05-08T13:00:00+00:00 | 2026-06-16T14:50:00+00:00 | `dedupe_required` | volatility_breakout, long_trend, market_structure, volatility_regime | none |
| `multi_symbol_ohlcv` | `True` | 236407 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XBTZEUR, XETHZEUR, XLMZEUR, XLTCZEUR, XRPZEUR, XXBTZEUR, XXLMZEUR, XXRPZEUR | 15m, 1h, 1m, 5m | 2026-05-08T13:00:00+00:00 | 2026-06-16T14:50:00+00:00 | `ready_for_cross_sectional_research` | cross_sectional_momentum, relative_value | none |
| `orderbook_depth_snapshots` | `True` | 434 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR | - | 2026-06-08T08:25:07.838741+00:00 | 2026-06-16T14:53:57.757583+00:00 | `sampled_top_of_book_depth` | order_flow_imbalance, liquidation_cascade, market_making | none |
| `spread_history` | `True` | 434 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR | - | 2026-06-08T08:25:07.838741+00:00 | 2026-06-16T14:53:57.757583+00:00 | `sampled_public_top_of_book` | cost_sensitive_intraday_filter, order_flow_imbalance | none |
| `funding_rates` | `False` | 0 | - | - | - | - | `missing` | - | funding_rates_missing |
| `futures_perp_prices` | `False` | 0 | - | - | - | - | `missing` | - | futures_perp_prices_missing |
| `spot_perp_basis` | `False` | 0 | - | - | - | - | `missing` | - | spot_perp_basis_missing |
| `open_interest` | `False` | 0 | - | - | - | - | `missing` | - | open_interest_missing |
| `liquidation_events` | `False` | 0 | - | - | - | - | `missing` | - | liquidation_events_missing |
| `volume_anomalies` | `True` | 236407 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XBTZEUR, XETHZEUR, XLMZEUR, XLTCZEUR, XRPZEUR, XXBTZEUR, XXLMZEUR, XXRPZEUR | 15m, 1h, 1m, 5m | 2026-05-08T13:00:00+00:00 | 2026-06-16T14:50:00+00:00 | `derived_from_ohlcv_volume` | volatility_breakout, liquidity_sweep_fakeout | none |
| `news_sentiment` | `False` | 0 | - | - | - | - | `missing` | - | news_sentiment_missing |
| `exchange_fees` | `True` | 24013 | - | - | - | - | `available_metadata` | all_cost_sensitive_research | none |
| `slippage_fill_history` | `False` | 0 | - | - | - | - | `ledger_without_cost_columns` | - | slippage_or_fee_history_missing |

## Alpha Families

| Family | Status | Capabilities | Blockers | Notes |
| --- | --- | --- | --- | --- |
| `cross_sectional_momentum` | `DATA_AVAILABLE_BUT_CURRENT_CONFIG_REJECTED_OR_BENCHMARK` | multi_symbol_ohlcv, exchange_fees | none | - |
| `funding_basis` | `DATA_MISSING` | spot_ohlcv | funding_rates_missing, spot_perp_basis_missing | do_not_run_until_real_derivatives_or_event_data_exists |
| `liquidation_cascade` | `DATA_MISSING` | spot_ohlcv, orderbook_depth_snapshots | liquidation_events_missing | do_not_run_until_real_derivatives_or_event_data_exists |
| `long_trend` | `DATA_AVAILABLE_BUT_CURRENT_CONFIG_REJECTED_OR_BENCHMARK` | spot_ohlcv, exchange_fees | none | - |
| `news_event_filter` | `DATA_MISSING` | - | news_sentiment_missing | - |
| `order_flow_imbalance` | `DATA_AVAILABLE_RESEARCH_ONLY` | orderbook_depth_snapshots, spread_history | none | top_of_book_samples_are_not_full_orderbook_replay |
| `relative_value` | `DATA_AVAILABLE_BUT_CURRENT_CONFIG_REJECTED_OR_BENCHMARK` | multi_symbol_ohlcv, exchange_fees | none | - |
| `volatility_breakout` | `DATA_AVAILABLE_BUT_CURRENT_CONFIG_REJECTED_OR_BENCHMARK` | spot_ohlcv, exchange_fees | none | - |

## Rejected Families Retest Gate

| Family | Status | Retest Allowed | Reason |
| --- | --- | ---: | --- |
| `cross_momentum` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `cross_momentum__leader_laggard_momentum` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `cross_sectional_momentum` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `dynamic_grid` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `grid` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `high_conviction_swing` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `long_trend` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `relative_value` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `trend_momentum` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |
| `volatility_breakout` | `REJECTED_CURRENT_CONFIG` | `False` | blocked_until_new_data_signature_or_new_template |

## OHLCV Backfill Plan

- `current_start_at`: `2026-05-08T13:00:00+00:00`
- `current_end_at`: `2026-06-16T14:50:00+00:00`
- `current_row_count`: `236407`
- `current_symbols`: `['AAVEEUR', 'ADAEUR', 'ATOMEUR', 'AVAXEUR', 'BCHEUR', 'BTCZEUR', 'DOTEUR', 'ETHZEUR', 'LINKEUR', 'LTCZEUR', 'SOLEUR', 'TRXEUR', 'XBTZEUR', 'XETHZEUR', 'XLMZEUR', 'XLTCZEUR', 'XRPZEUR', 'XXBTZEUR', 'XXLMZEUR', 'XXRPZEUR']`
- `current_timeframes`: `['15m', '1h', '1m', '5m']`
- `target_intraday_months_minimum`: `6`
- `target_intraday_months_preferred`: `12`
- `recommended_provider_priority`: `['kraken_public_ohlcv', 'ccxt_kraken_public_ohlcv', 'external_public_csv_if_verified']`
- `bounded_commands`: `['python -m autobot.v2.cli collect-history --run-id ohlcv_6m_bounded --symbols AAVEEUR,ADAEUR,ATOMEUR,AVAXEUR,BCHEUR,BTCZEUR,DOTEUR,ETHZEUR,LINKEUR,LTCZEUR,SOLEUR,TRXEUR,XBTZEUR,XETHZEUR,XLMZEUR,XLTCZEUR,XRPZEUR,XXBTZEUR,XXLMZEUR,XXRPZEUR --timeframes 15m,1h,1m,5m --start-at <UTC_START_6M> --end-at <UTC_END> --max-pages <bounded_pages> --dedupe true --output-dir data/research/historical_long', 'python -m autobot.v2.cli data-quality --run-id ohlcv_6m_quality --paths <deduped_csv_files> --output-dir reports/research/data_foundation', 'python -m autobot.v2.cli data-capability-scan --state-db data/autobot_state.db --data-roots data/research,reports/research --output-dir reports/research']`
- `storage_policy_notes`: `['Run as bounded batch only, never on each tick.', 'Keep raw exports and write canonical deduped files with manifest.', 'Do not retest rejected OHLCV hypotheses unless history grows significantly or a new template is introduced.']`
- `estimated_storage_multiplier_for_12m`: `9.3407`
- `status`: `plan_only`

## Derivatives / Event Data Plan

| Data | Status | Priority | Complexity | Sources | Unlocks | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `funding_rates` | `DATA_MISSING` | `high` | `medium` | kraken_futures_public_if_supported, ccxt_derivatives_public_if_supported, paid_derivatives_data_vendor | funding_basis | must be real funding feed, not inferred from spot OHLCV |
| `perp_mark_index_basis` | `DATA_MISSING` | `high` | `medium` | kraken_futures_public_if_supported, ccxt_derivatives_public_if_supported | funding_basis, spot_perp_basis | basis proxy from another venue must be marked proxy_low_confidence |
| `open_interest` | `DATA_MISSING` | `medium` | `medium` | kraken_futures_public_if_supported, ccxt_derivatives_public_if_supported, paid_derivatives_data_vendor | funding_basis, liquidation_cascade | use as context, not direct alpha without event validation |
| `liquidation_events` | `DATA_MISSING` | `medium` | `high` | paid_liquidation_feed, exchange_public_if_available | liquidation_cascade | do not create weak OHLCV liquidation proxy except proxy_low_confidence |

## Research Storage Policy

- `raw_data`: `Store provider-native exports under data/research/raw/<provider>/<capability>/ with immutable manifests.`
- `canonical_data`: `Write normalized symbol/timeframe datasets under data/research/canonical/ with schema/version metadata.`
- `deduped_data`: `Use symbol+timeframe+timestamp unique keys; deduped files are the only source for runner inputs.`
- `manifests`: `Each run writes row counts, duplicate counts, gaps, source provider, start/end and checksum where practical.`
- `retention`: `Keep critical ledgers, reports and manifests indefinitely; rotate raw high-frequency snapshots only after canonical verification.`
- `compression`: `Prefer Parquet or compressed CSV for long OHLCV/orderbook history when dependencies are available.`
- `safe_cleanup`: `['__pycache__', '.pytest_cache', 'temporary smoke configs', 'Docker build cache']`
- `protected_paths`: `['data/autobot_state.db', 'data/paper_trades.db', 'reports/research', 'reports/non_regression', 'backups', 'trade ledgers']`

## Scheduler Notes

- Do not relaunch rejected OHLCV templates solely because this scanner exists.
- Relaunch requires significant new data, a new historical period, a new thesis, or a genuinely different template.
- funding_basis blocked until funding, basis/perp and validated provider data exist.
- liquidation_cascade blocked until liquidation events and sufficient depth data exist.

## Safety

- Research-only data capability scan.
- No live trading, paper capital, promotion, shadow activation, sizing, leverage, UI, or runtime order path.
- No orders are created.
- Grid remains no-go.
- paper_capital_allowed: `False`
- live_allowed: `False`
- promotable: `False`
