# Paper vs Research Comparison - research_paper_parity_2026-06-06

Matrix run: `research_paper_parity_2026-06-06_matrix`
Paper source: `state_db_trade_ledger` / `data\vps_autobot_state_2026-06-04_2026-06-04_121159.db`
Buckets: `19`
Divergent buckets: `18`
Paper trades: `455`
Research trades: `973`
Paper net PnL EUR: `-21.397803`
Research net PnL EUR: `-456.926628`

## Triage Summary

Alignment counts: `{"no_evidence": 1, "paper_has_trades_research_missing": 13, "paper_missing_research_has_trades": 4, "paper_positive_research_negative": 1}`
Top diagnostics: `{"decision_trace_missing_for_bucket": 18, "no_comparable_trading_evidence": 1, "official_paper_missing_research_trades": 4, "paper_sample_too_small": 6, "research_adapter_missing_official_paper_trades": 13, "research_rejected_negative_net_pnl": 4, "research_sample_too_small": 1, "runtime_or_sample_difference": 1}`
Top warnings: `{"paper_research_divergence": 18, "paper_sample_below_30_trades": 6, "research_sample_below_30_trades": 1}`

### Priority Buckets

| Rank | Strategy | Symbol | Alignment | Paper Net | Research Net | Delta | Primary Diagnostic | Recommendation |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 1 | mean_reversion | XLMZEUR | paper_missing_research_has_trades | 0.000000 | -187.692667 | 187.692667 | official_paper_missing_research_trades | check_router_or_paper_gate_coverage |
| 2 | trend_momentum | XLMZEUR | paper_missing_research_has_trades | 0.000000 | -125.347928 | 125.347928 | official_paper_missing_research_trades | check_router_or_paper_gate_coverage |
| 3 | dynamic_grid | XLMZEUR | paper_missing_research_has_trades | 0.000000 | -109.605392 | 109.605392 | official_paper_missing_research_trades | check_router_or_paper_gate_coverage |
| 4 | mean_reversion | TRXEUR | paper_missing_research_has_trades | 0.000000 | -24.182263 | 24.182263 | official_paper_missing_research_trades | check_router_or_paper_gate_coverage |
| 5 | dynamic_grid | TRXEUR | paper_positive_research_negative | 0.885147 | -10.098377 | 10.983524 | runtime_or_sample_difference | investigate_runtime_or_sample_difference |
| 6 | dynamic_grid | XLTCZEUR | paper_has_trades_research_missing | -3.220020 | 0.000000 | -3.220020 | research_adapter_missing_official_paper_trades | check_research_adapter_coverage |
| 7 | dynamic_grid | XETHZEUR | paper_has_trades_research_missing | -3.071066 | 0.000000 | -3.071066 | research_adapter_missing_official_paper_trades | check_research_adapter_coverage |
| 8 | dynamic_grid | XXLMZEUR | paper_has_trades_research_missing | -2.633676 | 0.000000 | -2.633676 | research_adapter_missing_official_paper_trades | check_research_adapter_coverage |

## Buckets

| Strategy | Symbol | Paper Trades | Paper Net | Paper PF | Research Trades | Research Net | Research PF | Trace Count | Trace Missing | Delta | Alignment | Diagnostics | Recommendation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- | --- |
| trend_momentum | TRXEUR | 0 | 0.000000 |  | 0 | 0.000000 |  | 0 |  | 0.000000 | no_evidence | no_comparable_trading_evidence | collect_more_data |
| dynamic_grid | AAVEEUR | 35 | -2.225408 | 0.173577 | 0 | 0.000000 |  | 0 |  | -2.225408 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | ADAEUR | 26 | -1.164653 | 0.405494 | 0 | 0.000000 |  | 0 |  | -1.164653 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | ATOMEUR | 35 | -0.069840 | 0.964083 | 0 | 0.000000 |  | 0 |  | -0.069840 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | AVAXEUR | 10 | -0.360047 | 0.666045 | 0 | 0.000000 |  | 0 |  | -0.360047 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | BCHEUR | 22 | -1.695255 | 0.079734 | 0 | 0.000000 |  | 0 |  | -1.695255 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | DOTEUR | 18 | -2.138459 | 0.195200 | 0 | 0.000000 |  | 0 |  | -2.138459 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | LINKEUR | 31 | -1.641325 | 0.316276 | 0 | 0.000000 |  | 0 |  | -1.641325 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | SOLEUR | 22 | -1.184300 | 0.278345 | 0 | 0.000000 |  | 0 |  | -1.184300 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XETHZEUR | 35 | -3.071066 | 0.096066 | 0 | 0.000000 |  | 0 |  | -3.071066 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XLTCZEUR | 39 | -3.220020 | 0.037089 | 0 | 0.000000 |  | 0 |  | -3.220020 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XXBTZEUR | 56 | -1.363889 | 0.635999 | 0 | 0.000000 |  | 0 |  | -1.363889 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XXLMZEUR | 42 | -2.633676 | 0.127483 | 0 | 0.000000 |  | 0 |  | -2.633676 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XXRPZEUR | 27 | -1.515011 | 0.213664 | 0 | 0.000000 |  | 0 |  | -1.515011 | paper_has_trades_research_missing | research_adapter_missing_official_paper_trades, paper_sample_too_small, decision_trace_missing_for_bucket | check_research_adapter_coverage |
| dynamic_grid | XLMZEUR | 0 | 0.000000 |  | 246 | -109.605392 | 0.223828 | 0 |  | 109.605392 | paper_missing_research_has_trades | official_paper_missing_research_trades, research_rejected_negative_net_pnl, decision_trace_missing_for_bucket | check_router_or_paper_gate_coverage |
| mean_reversion | TRXEUR | 0 | 0.000000 |  | 38 | -24.182263 | 0.000000 | 0 |  | 24.182263 | paper_missing_research_has_trades | official_paper_missing_research_trades, research_rejected_negative_net_pnl, decision_trace_missing_for_bucket | check_router_or_paper_gate_coverage |
| mean_reversion | XLMZEUR | 0 | 0.000000 |  | 420 | -187.692667 | 0.144786 | 0 |  | 187.692667 | paper_missing_research_has_trades | official_paper_missing_research_trades, research_rejected_negative_net_pnl, decision_trace_missing_for_bucket | check_router_or_paper_gate_coverage |
| trend_momentum | XLMZEUR | 0 | 0.000000 |  | 258 | -125.347928 | 0.253206 | 0 |  | 125.347928 | paper_missing_research_has_trades | official_paper_missing_research_trades, research_rejected_negative_net_pnl, decision_trace_missing_for_bucket | check_router_or_paper_gate_coverage |
| dynamic_grid | TRXEUR | 57 | 0.885147 | 1.482212 | 11 | -10.098377 | 0.001461 | 0 |  | 10.983524 | paper_positive_research_negative | runtime_or_sample_difference, research_sample_too_small, decision_trace_missing_for_bucket | investigate_runtime_or_sample_difference |

## Warnings

- realized_pnl_missing:f77e9c0e
- realized_pnl_missing:f1575f3a
- realized_pnl_missing:e4f87f6a
- realized_pnl_missing:dd342f29
- realized_pnl_missing:ffd01f1c
- realized_pnl_missing:dd6fee0b
- realized_pnl_missing:ffd01f1c
- realized_pnl_missing:d328bf4b
- realized_pnl_missing:a3cba431
- realized_pnl_missing:cca9e92e
- realized_pnl_missing:96dc39ae
- realized_pnl_missing:c6b66367
- realized_pnl_missing:680e0b51
- realized_pnl_missing:680e0b51
- realized_pnl_missing:c398ea7e
- realized_pnl_missing:5e27e2ef
- realized_pnl_missing:b046a2cf
- realized_pnl_missing:ff71f846
- realized_pnl_missing:ba067bf3
- realized_pnl_missing:aaba7fd6
- realized_pnl_missing:59a86bd1
- realized_pnl_missing:e57f42c9
- realized_pnl_missing:e57f42c9
- realized_pnl_missing:e8c0fa53
- realized_pnl_missing:b40cc2dd
- realized_pnl_missing:ac4dd380
- realized_pnl_missing:a4710067
- realized_pnl_missing:44878d56
- realized_pnl_missing:44878d56
- realized_pnl_missing:b1e6506c
- realized_pnl_missing:d030377d
- realized_pnl_missing:e14750b6
- realized_pnl_missing:27eac4c0
- realized_pnl_missing:d789613b
- realized_pnl_missing:1471ae5c
- realized_pnl_missing:d4369fc7
- realized_pnl_missing:aed58910
- realized_pnl_missing:446f6f1b
- realized_pnl_missing:f71ae8cb
- realized_pnl_missing:eaab1d8b
- realized_pnl_missing:a6a00a0a
- realized_pnl_missing:a23cbd51
- realized_pnl_missing:f9d3b532
- realized_pnl_missing:cf2c3a7b
- realized_pnl_missing:9a533fa0
- realized_pnl_missing:6e75a9d6
- realized_pnl_missing:c2062cfc
- realized_pnl_missing:677bb800
- realized_pnl_missing:986be504
- realized_pnl_missing:c9860283
- realized_pnl_missing:769e0a81
- realized_pnl_missing:50da35d5
- realized_pnl_missing:57d8b651
- realized_pnl_missing:4073dc1c
- realized_pnl_missing:3ad71cf1
- realized_pnl_missing:18f1fa8d
- realized_pnl_missing:1306d518
- realized_pnl_missing:f7bd262a
- realized_pnl_missing:f3be9c81
- realized_pnl_missing:f274ac35
- realized_pnl_missing:d9aa9a8f
- realized_pnl_missing:cfc9df01
- realized_pnl_missing:c7fa3e7b
- realized_pnl_missing:c19c99dc
- realized_pnl_missing:bf6e8bce
- realized_pnl_missing:da5c1925
- realized_pnl_missing:da5c1925
- realized_pnl_missing:adde0b73
- realized_pnl_missing:5e0d8b9f
- realized_pnl_missing:a508072d
- realized_pnl_missing:c5db8a1d
- realized_pnl_missing:a56e371b
- realized_pnl_missing:a56e371b
- realized_pnl_missing:a56e371b
- realized_pnl_missing:7e6f251d
- realized_pnl_missing:7b70524c
- realized_pnl_missing:f65d384d
- realized_pnl_missing:f65d384d
- realized_pnl_missing:f65d384d
- realized_pnl_missing:7589b420
- realized_pnl_missing:59130ef2
- realized_pnl_missing:2ed62267
- realized_pnl_missing:d7c8b650
- realized_pnl_missing:dc712f5e
- realized_pnl_missing:ee85a4b5
- realized_pnl_missing:ee85a4b5
- realized_pnl_missing:bb3a9f23
- realized_pnl_missing:dba70009
- realized_pnl_missing:b7ca3a40
- realized_pnl_missing:d6557df0
- realized_pnl_missing:b048bf30
- realized_pnl_missing:c0c64a76
- realized_pnl_missing:a5a166fe
- realized_pnl_missing:a5a166fe
- realized_pnl_missing:93c9fd28
- realized_pnl_missing:80590685
- realized_pnl_missing:d58d7cdb
- opening_leg_missing:d58d7cdb
- realized_pnl_missing:852ee556
- opening_leg_missing:852ee556
- opening_leg_missing:1219cd03
- realized_pnl_missing:6b56959a
- opening_leg_missing:a7b1be25
- realized_pnl_missing:78f68863
- opening_leg_missing:78f68863
- slippage_bps_anomaly:07d4b43a
- slippage_bps_anomaly:0814accc
- slippage_bps_anomaly:171b16eb
- slippage_bps_anomaly:30530b85
- slippage_bps_anomaly:086c0232
- slippage_bps_anomaly:2fc32aad
- slippage_bps_anomaly:281fef3c
- slippage_bps_anomaly:49be5fcc
- slippage_bps_anomaly:4d3a0d4e
- slippage_bps_anomaly:4e106251
- slippage_bps_anomaly:5608e0bd
- slippage_bps_anomaly:67579ef7
- slippage_bps_anomaly:7d96e433
- slippage_bps_anomaly:97cc3b96
- slippage_bps_anomaly:9e3dfafb
- slippage_bps_anomaly:ce2ede39
- slippage_bps_anomaly:d0c9e506
- slippage_bps_anomaly:c38ba368
- slippage_bps_anomaly:7b643b29
- slippage_bps_anomaly:4488d16d
- slippage_bps_anomaly:83daf612

## Safety

- Read-only paper/research comparison.
- No paper or live order is created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
