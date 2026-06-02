# Decision Trace Audit - vps_2026_06_02_decision_trace_audit

## Summary

- Traces: `8948`
- Stored trace sample: `500` / `500`
- Canonical complete traces: `455`
- Canonical complete ratio: `5.08%`
- Signal without decision: `857`
- Rejected traces: `2490`
- Rejected with outcome: `1241`
- Execution traces: `5699`
- Execution complete: `0`
- Orphan orders: `0`
- Orphan trades: `555`
- Total linked net PnL EUR: `-21.397803`

## Missing Stages

| Stage | Count |
| --- | ---: |
| decision | 7342 |
| signal | 7342 |
| pnl | 5146 |
| trade | 5002 |
| outcome | 1249 |

## Event Types

| Event Type | Count |
| --- | ---: |
| decision | 1606 |
| signal | 1606 |

## Top Incomplete Traces

| Trace | Symbol | Engine | Statuses | Missing | Net PnL | Reasons |
| --- | --- | --- | --- | --- | ---: | --- |
| decision_id:dec_b58ca24a2c6a47d485d38a7a7bea3d70 | ETHEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_9267200534da41d4b6215a35533a4e87 | ETHEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_08c96142f0ec42abbbbbf92e95dc0672 | ETHEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_6b2c0cce82644704b0a44ce0722a378d | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_e3d21dc785784b32ad0ff843f91ea8e9 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_8823af88549341928602dd646bbc73b5 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_65435fd0b4b748d8acb34a8b26b2103a | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_7f70a77ca2ac4f1f99dbb8360686fc05 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_4141ec94c6b94e2ca0c43691ae8372c0 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_28ac497c82194dd09bd033da4cdc29a5 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_ed084a7412ea49768bed7d76592486d3 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_c38fadd2a9bf4f36868afb799196138b | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_7f46b35514c94df2b0fcbdab3dd050f5 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_5910cc7d91e644cdbb17e65fefb0a1ac | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_67484917ea394437b1c522bf65568ac5 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_408c5a2e795a422cbc676fe1fc4c3551 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_f3e80769292d4c228869e61040d3e928 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_06511943cc3a4309bcf7bd4915411504 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_2f09aa6e2ee24f6ca3becdfa65e46086 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_aa84a272e5c94ec1b360398e2c1f83e8 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_2790249ea2f1439f8eedaabb5614c7a0 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_aabcd59b7706481281612b540e51fd2a | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_e6eb7b2c5f0c40889dde01bc453f392a | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_da185184ac304eb880536985fa2656aa | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_56024df632d34b6d8330d4355441d140 | SOLEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_2cc38fdd61b640909632df0c5ccc35b9 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_cc4fa46f7f4d40f19a03cbcc917b988f | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_3cc1fb78f1824cb9b007a68d0c8c1d7c | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_70eae04fe767411a9b38102dc2de107d | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_33703f0dc00e4330ba3eccd1513effa5 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_03f5d135f1874e99a38a7f592c2c6326 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_a83be082c91240b8bdf903f2083503af | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_c3590d52fe834e22bd47fc77b623b73f | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_1d6d5733d7304e778a43a35a7b207fba | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_3307e2f4c49347e788a5c9cd2e4ce81a | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_ba295bbe475e49fcbdb377c5f726c647 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_928caeed80904bce84335cba6ae5bba4 | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_c3b0283305154a599e3f331097316d21 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_ed64f14e31414f85a4f3b82c495bb663 | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_4932e35748704f5eb3f4d2338e75dc63 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_d7b22d7e78c6488fbd5dcacb65a80ae7 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_bb70e43208924de48240ed86fcf3a4a3 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_c53d7119c09947e58ef29ac801e71a84 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_fb16d2de84904be2b6f9b4222687d3e6 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_393a9e40c7af48d3913f2c7cd7cb088c | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_b8621dc5814545ba84ed06bcc2c0a6f0 | XETHZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_2a16c0a3000043dc99cdaa6c7f0650f1 | XXBTZEUR |  | REJECTED | signal, decision, outcome | 0.000000 |  |
| decision_id:dec_8fd6ad4c57444664be56277157bf6aa0 | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_9793a388f44b4081b1abdc94dbe147ce | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |
| decision_id:dec_efa70cef577347589b44e86f161ed7d5 | XLTCZEUR |  | FILLED | signal, decision, trade, pnl | 0.000000 |  |

## Safety

This audit is read-only and research-only. It does not authorize paper or live execution.
