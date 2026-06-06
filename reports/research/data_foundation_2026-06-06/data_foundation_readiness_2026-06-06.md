# Data Foundation Readiness - data_foundation_readiness_2026-06-06

Generated at: `2026-06-06T16:47:46.326367+00:00`
Overall status: `not_ready`
Usable files: `0`
Unusable files: `3`

## Dataset Files

| Source | Rows | Symbols | Timeframes | Start | End | Gaps | Duplicates | Volume | Bid/Ask | Depth | Usable | Warnings |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| data\research\vps_2026_06_04_dataset_canonical_smoke\vps_2026_06_04_dataset_canonical_smoke_1m.csv | 80920 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR | 1m | 2026-05-28T09:48:00+00:00 | 2026-06-04T09:53:00+00:00 | 18129 | 0 | absent_or_zero | no | no | no | data_gaps_detected, data_gaps_present, volume_absent, bid_ask_absent, order_book_depth_absent |
| data\research\vps_2026_06_04_dataset_canonical_smoke\vps_2026_06_04_dataset_canonical_smoke_5m.csv | 24003 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR | 5m | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:50:00+00:00 | 23989 | 0 | absent_or_zero | no | no | no | data_gaps_detected, data_gaps_present, volume_absent, bid_ask_absent, order_book_depth_absent |
| data\research\vps_2026_06_04_dataset_canonical_smoke\vps_2026_06_04_dataset_canonical_smoke_15m.csv | 9089 | AAVEEUR, ADAEUR, ATOMEUR, AVAXEUR, BCHEUR, BTCZEUR, DOTEUR, ETHZEUR, LINKEUR, LTCZEUR, SOLEUR, TRXEUR, XLMZEUR, XRPZEUR | 15m | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:45:00+00:00 | 9075 | 0 | absent_or_zero | no | no | no | data_gaps_detected, data_gaps_present, volume_absent, bid_ask_absent, order_book_depth_absent |

## Symbol Coverage

| Symbol | Files | Rows | Start | End | Warnings |
| --- | ---: | ---: | --- | --- | --- |
| AAVEEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| ADAEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| ATOMEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| AVAXEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| BCHEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| BTCZEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| DOTEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| ETHZEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| LINKEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| LTCZEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| SOLEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| TRXEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| XLMZEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |
| XRPZEUR | 3 | 114012 | 2026-05-28T09:45:00+00:00 | 2026-06-04T09:53:00+00:00 | bid_ask_absent, data_gaps_detected, data_gaps_present, order_book_depth_absent, volume_absent |

## Recommendations

- Use exchange OHLCV history for research conclusions; keep market_price_samples as runtime diagnostics only.
- Do not promote any strategy unless the tested dataset includes costs and sufficient out-of-sample windows.
- Prefer Kraken REST/CCXT OHLCV exports because market_price_samples has no real volume.
- Collect bid/ask or order-book snapshots before trusting intraday cost-sensitive strategies.
- Exclude or repair datasets with gaps before batch validation.
- Databento is not the first priority for Kraken spot crypto here; public Kraken OHLCV plus local bid/ask/depth capture closes the immediate parity gap with less vendor complexity.

## Safety

- Research data-quality report only.
- No runtime paper/live service is started.
- No paper or live order is created.
- No Kraken order can be created by this report.
- No live trading permission is granted.
