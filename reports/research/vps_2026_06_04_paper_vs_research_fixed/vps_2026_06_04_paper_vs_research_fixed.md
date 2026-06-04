# Paper vs Research Comparison - vps_2026_06_04_paper_vs_research_fixed

Matrix run: `vps_2026_06_04_top14`
Paper source: `state_db_trade_ledger` / `C:\Users\flore\Documents\Codex\2026-04-27\bonjour-voil-j-ai-utilis-r\Projet_AUTOBOT\data\vps_autobot_state_2026-06-04_2026-06-04_121159.db`
Buckets: `56`
Divergent buckets: `55`
Paper trades: `455`
Research trades: `2603`
Paper net PnL EUR: `-21.397803`
Research net PnL EUR: `-1454.810159`

## Buckets

| Strategy | Symbol | Paper Trades | Paper Net | Paper PF | Research Trades | Research Net | Research PF | Delta | Alignment | Recommendation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| trend_momentum | TRXEUR | 0 | 0.000000 |  | 0 | 0.000000 |  | 0.000000 | no_evidence | collect_more_data |
| unknown | AAVEEUR | 35 | -2.225408 | 0.173577 | 0 | 0.000000 |  | -2.225408 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | ADAEUR | 26 | -1.164653 | 0.405494 | 0 | 0.000000 |  | -1.164653 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | ATOMEUR | 35 | -0.069840 | 0.964083 | 0 | 0.000000 |  | -0.069840 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | AVAXEUR | 10 | -0.360047 | 0.666045 | 0 | 0.000000 |  | -0.360047 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | BCHEUR | 22 | -1.695255 | 0.079734 | 0 | 0.000000 |  | -1.695255 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | DOTEUR | 18 | -2.138459 | 0.195200 | 0 | 0.000000 |  | -2.138459 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | LINKEUR | 31 | -1.641325 | 0.316276 | 0 | 0.000000 |  | -1.641325 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | SOLEUR | 22 | -1.184300 | 0.278345 | 0 | 0.000000 |  | -1.184300 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | TRXEUR | 57 | 0.885147 | 1.482212 | 0 | 0.000000 |  | 0.885147 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | XETHZEUR | 35 | -3.071066 | 0.096066 | 0 | 0.000000 |  | -3.071066 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | XLTCZEUR | 39 | -3.220020 | 0.037089 | 0 | 0.000000 |  | -3.220020 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | XXBTZEUR | 56 | -1.363889 | 0.635999 | 0 | 0.000000 |  | -1.363889 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | XXLMZEUR | 42 | -2.633676 | 0.127483 | 0 | 0.000000 |  | -2.633676 | paper_has_trades_research_missing | check_research_adapter_coverage |
| unknown | XXRPZEUR | 27 | -1.515011 | 0.213664 | 0 | 0.000000 |  | -1.515011 | paper_has_trades_research_missing | check_research_adapter_coverage |
| dynamic_grid | AAVEEUR | 0 | 0.000000 |  | 43 | -22.456307 | 0.190116 | 22.456307 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | ADAEUR | 0 | 0.000000 |  | 38 | -27.827787 | 0.039403 | 27.827787 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | ATOMEUR | 0 | 0.000000 |  | 29 | -28.762743 | 0.095706 | 28.762743 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | AVAXEUR | 0 | 0.000000 |  | 42 | -29.101712 | 0.099938 | 29.101712 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | BCHEUR | 0 | 0.000000 |  | 52 | -37.003405 | 0.096212 | 37.003405 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | BTCZEUR | 0 | 0.000000 |  | 29 | -23.224843 | 0.005680 | 23.224843 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | DOTEUR | 0 | 0.000000 |  | 39 | -27.065182 | 0.115788 | 27.065182 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | ETHZEUR | 0 | 0.000000 |  | 30 | -24.094084 | 0.032420 | 24.094084 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | LINKEUR | 0 | 0.000000 |  | 39 | -24.253805 | 0.117646 | 24.253805 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | LTCZEUR | 0 | 0.000000 |  | 26 | -18.155558 | 0.034970 | 18.155558 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | SOLEUR | 0 | 0.000000 |  | 35 | -25.286387 | 0.040435 | 25.286387 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | TRXEUR | 0 | 0.000000 |  | 11 | -10.098377 | 0.001461 | 10.098377 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | XLMZEUR | 0 | 0.000000 |  | 265 | -109.914138 | 0.241679 | 109.914138 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| dynamic_grid | XRPZEUR | 0 | 0.000000 |  | 35 | -28.686196 | 0.018910 | 28.686196 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | AAVEEUR | 0 | 0.000000 |  | 51 | -30.132859 | 0.132932 | 30.132859 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | ADAEUR | 0 | 0.000000 |  | 145 | -80.844488 | 0.015438 | 80.844488 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | ATOMEUR | 0 | 0.000000 |  | 59 | -35.485795 | 0.073323 | 35.485795 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | AVAXEUR | 0 | 0.000000 |  | 73 | -28.284236 | 0.164212 | 28.284236 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | BCHEUR | 0 | 0.000000 |  | 78 | -57.416952 | 0.058103 | 57.416952 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | BTCZEUR | 0 | 0.000000 |  | 102 | -50.866171 | 0.013210 | 50.866171 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | DOTEUR | 0 | 0.000000 |  | 84 | -46.573436 | 0.084215 | 46.573436 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | ETHZEUR | 0 | 0.000000 |  | 129 | -67.283913 | 0.007075 | 67.283913 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | LINKEUR | 0 | 0.000000 |  | 99 | -59.741526 | 0.040773 | 59.741526 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | LTCZEUR | 0 | 0.000000 |  | 129 | -72.282178 | 0.006722 | 72.282178 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | SOLEUR | 0 | 0.000000 |  | 161 | -95.029858 | 0.006583 | 95.029858 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | TRXEUR | 0 | 0.000000 |  | 38 | -24.182263 | 0.000000 | 24.182263 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | XLMZEUR | 0 | 0.000000 |  | 196 | -99.170191 | 0.174665 | 99.170191 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| mean_reversion | XRPZEUR | 0 | 0.000000 |  | 150 | -74.723523 | 0.009547 | 74.723523 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | AAVEEUR | 0 | 0.000000 |  | 20 | -12.761854 | 0.154944 | 12.761854 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | ADAEUR | 0 | 0.000000 |  | 24 | -12.766190 | 0.134603 | 12.766190 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | ATOMEUR | 0 | 0.000000 |  | 23 | -14.262376 | 0.006786 | 14.262376 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | AVAXEUR | 0 | 0.000000 |  | 23 | -12.413953 | 0.106178 | 12.413953 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | BCHEUR | 0 | 0.000000 |  | 34 | -18.038597 | 0.239967 | 18.038597 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | BTCZEUR | 0 | 0.000000 |  | 6 | -1.270525 | 0.302640 | 1.270525 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | DOTEUR | 0 | 0.000000 |  | 34 | -17.496971 | 0.157238 | 17.496971 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | ETHZEUR | 0 | 0.000000 |  | 13 | -5.773907 | 0.068773 | 5.773907 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | LINKEUR | 0 | 0.000000 |  | 20 | -4.645811 | 0.507381 | 4.645811 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | LTCZEUR | 0 | 0.000000 |  | 9 | -2.839674 | 0.286073 | 2.839674 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | SOLEUR | 0 | 0.000000 |  | 15 | -5.652711 | 0.190889 | 5.652711 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | XLMZEUR | 0 | 0.000000 |  | 158 | -82.796527 | 0.346053 | 82.796527 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |
| trend_momentum | XRPZEUR | 0 | 0.000000 |  | 17 | -6.143151 | 0.117848 | 6.143151 | paper_missing_research_has_trades | check_router_or_paper_gate_coverage |

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

## Safety

- Read-only paper/research comparison.
- No paper or live order is created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
