# AUTOBOT Performance Audit Brief For GPT-5.5

Date: 2026-05-31
Commit observed on VPS: `96fce31`
Mode: `paper`
Live trading: disabled

## Copy-Paste Prompt

Tu es GPT-5.5 et tu dois auditer AUTOBOT, un système de trading algorithmique crypto paper-first sur Kraken spot EUR.

Objectif: déterminer pourquoi la performance officielle paper est négative malgré plusieurs couches de scoring, shadow labs, regime detection, validation quant et garde-fous. Ne propose pas de baisse agressive des seuils ni de passage live. Je veux une analyse de structure, de stratégie, de données, d'exécution, de coûts, de validation et de risk management.

Contexte système:

- Pipeline cible: `MarketData -> Signal -> OpportunityScore -> PortfolioAllocation -> RiskCheck -> ExecutionCommand -> Fill -> Position -> PnL -> Ledger -> Dashboard`.
- AUTOBOT tourne en paper avec 14 instances/paires.
- Le container VPS est healthy, orchestrateur running, websocket connected.
- Le compte Kraken live n'est pas connecté pour trading réel dans ce contexte; aucun ordre live ne doit être envoyé.
- Capital paper actif affiché: `800 EUR`.
- Budget paper référence utilisateur futur live: `500 EUR`.
- Les shadow labs peuvent continuer même en futur live, mais ne doivent jamais promouvoir automatiquement une stratégie.

Performance officielle paper actuelle:

- Source de vérité PnL: `trade_ledger`.
- Closed trades officiels: `555`.
- PnL net officiel total: `-21.397803 EUR`.
- Profit factor officiel: `0.361`.
- Win rate officiel: `26.85%`.
- Expectancy moyenne: `-0.038555 EUR/trade`.
- Frais sur clôtures: `10.183481 EUR`.
- Interprétation: AUTOBOT apprend/observe mais la stratégie officielle paper n'est pas rentable en agrégé.

Performance officielle par paire:

| Symbol | Closes | PnL EUR | PF | Win Rate | Expectancy |
| --- | ---: | ---: | ---: | ---: | ---: |
| TRXEUR | 59 | 0.885147 | 1.4822 | 52.54% | 0.015002 |
| ATOMEUR | 43 | -0.069840 | 0.9641 | 58.14% | -0.001624 |
| AVAXEUR | 10 | -0.360047 | 0.6660 | 10.00% | -0.036005 |
| ADAEUR | 39 | -1.164653 | 0.4055 | 23.08% | -0.029863 |
| SOLEUR | 37 | -1.184300 | 0.2783 | 16.22% | -0.032008 |
| XXBTZEUR | 63 | -1.363889 | 0.6360 | 31.75% | -0.021649 |
| XXRPZEUR | 33 | -1.515011 | 0.2137 | 27.27% | -0.045909 |
| LINKEUR | 34 | -1.641325 | 0.3163 | 41.18% | -0.048274 |
| BCHEUR | 23 | -1.695255 | 0.0797 | 17.39% | -0.073707 |
| DOTEUR | 25 | -2.138459 | 0.1952 | 16.00% | -0.085538 |
| AAVEEUR | 48 | -2.225408 | 0.1736 | 18.75% | -0.046363 |
| XXLMZEUR | 52 | -2.633676 | 0.1275 | 19.23% | -0.050648 |
| XETHZEUR | 41 | -3.071066 | 0.0961 | 12.20% | -0.074904 |
| XLTCZEUR | 48 | -3.220020 | 0.0371 | 4.17% | -0.067084 |

Shadow labs:

- `setup_shadow_lab.db`: grid variants have strong positive evidence on `XXLMZEUR`, especially:
  - `XXLMZEUR / grid_wide`: 139 closes, `+24.300082 EUR`, expectancy `0.174821`.
  - `XXLMZEUR / grid_balanced`: 155 closes, `+19.423937 EUR`, expectancy `0.125316`.
  - `XXLMZEUR / grid_tight_range`: 162 closes, `+18.584146 EUR`, expectancy `0.114717`.
  - `XXLMZEUR / grid_defensive_observe`: 143 closes, `+15.481636 EUR`, expectancy `0.108263`.
  - `XXLMZEUR / grid_volatility`: 145 closes, `+14.136190 EUR`, expectancy `0.097491`.
- `trend_shadow_lab.db`: trend variants show positive evidence mostly on `XXLMZEUR`, but samples are smaller:
  - `XXLMZEUR / trend_breakout_balanced`: 12 closes, `+11.880516 EUR`.
  - `XXLMZEUR / trend_ema_momentum`: 25 closes, `+9.820212 EUR`.
  - `XXLMZEUR / trend_volatility_breakout`: 15 closes, `+6.439257 EUR`.
  - `XXLMZEUR / trend_breakout_slow`: 15 closes, `+2.570764 EUR`.
- `mean_reversion_shadow_lab.db`: evidence is weak/small-sample, with several positive tiny samples but no robust proof.

Important interpretation:

- Official paper and shadow labs diverge materially.
- `XXLMZEUR` looks attractive in shadow but negative in official paper.
- This suggests a likely issue in one or more of:
  - shadow fill model too optimistic;
  - official paper routing not selecting/promoting the winning variant correctly;
  - mismatch between shadow assumptions and official execution costs;
  - strategy governance blocking the right setup or letting poor setups execute;
  - timestamp/data-quality mismatch;
  - open/close accounting mismatch;
  - fees/spread/slippage/liquidity model mismatch.

Current validation architecture:

- Strategy registry exists: `docs/research/strategy_hypotheses.json`.
- Workflow statuses exist: `learning`, `candidate`, `backtest_passed`, `walk_forward_passed`, `shadow_passed`, `paper_validated`, `rejected`, `retired_from_execution`.
- Live auto-promotion is disabled.
- Acceptance gates include:
  - minimum closed trades: 30;
  - minimum paper closed trades: 100;
  - minimum profit factor: 1.25;
  - minimum paper PF: 1.2;
  - max paper drawdown: 10%;
  - fees required;
  - slippage required;
  - baseline required;
  - regime breakdown required;
  - reconciliation required.

New validation harness state:

- `research_validation_harness.py` exists and is isolated from live.
- It supports replay pipeline with simulated execution, ledger, metrics and baselines.
- It now has read-only loaders for:
  - `market_price_samples` from `autobot_state.db`;
  - `trade_ledger`;
  - `paper_trades.db`.
- On VPS, loader probe confirmed:
  - market samples loaded: 25 limited probe;
  - trade ledger events loaded: 25 limited probe;
  - paper trade events loaded: 25 limited probe.
- First example report was synthetic only:
  - `trend_momentum_replay_example_2026_05_29`;
  - 11 events;
  - 1 closed trade;
  - net PnL `+0.313321 EUR`;
  - buy-and-hold baseline `+14.344031 EUR`;
  - decision: `keep_testing`, insufficient sample.

Runtime/data quality observations:

- Websocket connected.
- 14 ticker pairs subscribed and 14 book pairs subscribed.
- Backpressure active at the time of observation:
  - message rate around `119 msg/s`;
  - backpressure threshold `100 msg/s`;
  - consecutive backpressure windows observed.
- Market data DB size on VPS:
  - `autobot_state.db`: about 41 MB;
  - `market_price_samples`: 68,256 rows;
  - `decision_ledger`: 2,978 rows;
  - `signal_outcomes`: 1,657 rows;
  - `trade_ledger`: 1,142 rows;
  - `orders`: 5,811 rows;
  - `order_state_transitions`: 17,270 rows.

Known blockers / symptoms:

- Official paper PF is far below live-readiness.
- Most pairs are negative.
- `TRXEUR` is the only positive official pair but with small absolute PnL.
- `XXLMZEUR` is strongly positive in shadow but negative officially.
- Paper trades DB contains many filled buys and many cancelled sells; verify if this reflects stale/cancelled exits, replacement orders, or expected lifecycle.
- Strategy governance logs often pause grid buys due to:
  - `setup optimizer gate`;
  - `pause_current_setup_and_test_selected_variant_in_paper`;
  - `router_selected_no_trade`;
  - `pause_grid_review_divergence`;
  - `do_not_promote_shadow_review_costs_and_execution`.
- Market data quality recovered many invalid order books historically, especially repeated resubscriptions for some pairs.
- Backpressure may reduce timeliness or distort signal/execution timing.

Research/audit tasks requested:

1. Determine whether official negative PnL comes mainly from:
   - bad strategy logic;
   - wrong market regime;
   - bad variant selection;
   - too optimistic shadow lab;
   - execution/accounting mismatch;
   - order lifecycle issue;
   - costs/spread/slippage exceeding targets;
   - insufficient market data quality;
   - lack of train/test/walk-forward validation.

2. Compare official paper vs shadow:
   - For each symbol/variant, reconstruct what shadow wanted to do and what official paper actually did.
   - Explain why `XXLMZEUR` shadow is positive while official `XXLMZEUR` is negative.
   - Identify whether the selected official variant matches the best shadow variant.
   - Check whether official execution uses the same fees, slippage, spread, TP/SL and sizing assumptions.

3. Audit the paper execution path:
   - Are sells cancelled too often?
   - Are exits replaced correctly?
   - Are positions closed by TP/SL or by governance?
   - Are cancelled sell rows harmless lifecycle noise or a bug?
   - Are open positions marked-to-market correctly?
   - Is realized PnL net of both entry and exit costs?

4. Audit opportunity/risk gates:
   - Is the router too conservative after bad historical PF?
   - Is it blocking valid signals because historical official paper is negative?
   - Is it letting weak grid setups trade despite poor pair health?
   - Are cost guard, ATR, spread and microstructure filters calibrated per symbol?

5. Audit data quality:
   - Does websocket backpressure affect timestamps, price freshness or missed order-book updates?
   - Are `market_price_samples` sufficient for event-driven replay?
   - Are book snapshots aligned with ticker prices at decision time?
   - Are invalid books creating false rejects or stale spread estimates?

6. Audit validation methodology:
   - Build or improve event-driven replay from real `market_price_samples`.
   - Add walk-forward validation.
   - Add baseline bundle for every strategy: no-trade, buy-and-hold, random same-frequency, previous-grid baseline.
   - Add regime-split performance.
   - Add out-of-sample parameter freeze.
   - Add cost stress: fees/spread/slippage multiples.
   - Add PBO/DSR only when sample size is sufficient.

7. Decide next improvement:
   - Do not add a new strategy first.
   - First reconcile official paper vs shadow.
   - Then fix execution/accounting/selection mismatches.
   - Then promote only variants that survive real replay + baseline + paper validation.

Rules:

- Do not activate live trading.
- Do not suggest lowering global thresholds just to force trades.
- Do not treat shadow evidence as proof.
- Do not optimize for last-sample PnL.
- Do not trust PnL unless it is net of fees and slippage.
- Do not recommend large architecture rewrites unless a smaller measurable fix is insufficient.

Expected output:

1. Root-cause hypotheses ranked by probability.
2. Data tables or queries needed to confirm each hypothesis.
3. Minimal code/architecture changes to test each hypothesis.
4. Metrics that would prove improvement.
5. A staged plan:
   - immediate audit queries;
   - reconciliation fixes;
   - replay validation;
   - paper-only trial;
   - promotion criteria.
6. Explicit statement on whether AUTOBOT is currently live-ready. Expected answer should likely be no unless evidence proves otherwise.

## My Current Working Diagnosis

AUTOBOT is operationally stable but not performance-validated. The strongest signal is not that "all pairs are bad"; it is that shadow simulations and official paper disagree. That disagreement must be explained before any strategy change can be trusted.

The highest priority is therefore:

1. Reconcile `XXLMZEUR` shadow winners against official `XXLMZEUR` paper losers.
2. Run the new event-driven replay harness on real `market_price_samples`, not synthetic data.
3. Compare official fills against simulated fills under the same fee/spread/slippage assumptions.
4. Verify sell cancellation/order lifecycle is not suppressing profitable exits.
5. Quantify backpressure/data-quality impact on decisions.

If those checks show the shadow labs were optimistic, fix the simulator before changing strategies. If they show official routing is failing to select the right variants, fix the router/governance bridge before adding new indicators.
