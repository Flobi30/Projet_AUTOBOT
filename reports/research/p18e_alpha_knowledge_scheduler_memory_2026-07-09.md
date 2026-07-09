# P18E - Alpha Knowledge Base + Bounded Scheduler + Research Memory

Date: 2026-07-09  
Commit code deployed for run: `3e2a9deade93396133dc37f082461c106d14af7e`  
Mode: research-only

## Objective

P18E adds a durable research workflow so AUTOBOT no longer depends on manual strategy selection by Codex. AUTOBOT can now:

- maintain a bounded alpha-family knowledge base;
- load strategy templates with strict limits;
- track research trials and rejected configurations;
- rank the next hypothesis to test from data, adapters and memory;
- stop weak hypotheses automatically;
- avoid any paper/live/promotion or runtime order path change.

## Files Added / Changed

- `docs/research/alpha_knowledge_base.json`
- `docs/research/strategy_templates.json`
- `reports/research/alpha_research_memory.json`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`

## Alpha Families

Created 13 bounded alpha families:

- `trend_momentum`
- `mean_reversion`
- `volatility_breakout`
- `cross_sectional_momentum`
- `relative_value`
- `funding_basis`
- `liquidation_cascade`
- `order_flow_imbalance`
- `volatility_regime`
- `market_structure`
- `news_event_filter`
- `arbitrage_cross_exchange`
- `market_making`

All families are metadata/research definitions only. None can activate paper, live, shadow, sizing, leverage, or order paths.

## Strategy Templates

Created 7 bounded templates:

- `breakout_after_compression`
- `leader_laggard_momentum`
- `regime_filtered_trend`
- `volatility_reversal_after_extension`
- `funding_extreme_reversion`
- `liquidation_recovery`
- `relative_strength_rotation`

Each template declares:

- required adapter;
- allowed parameter ranges;
- max variants;
- max symbols;
- max runtime seconds;
- forbidden optimizations;
- anti-lookahead rules;
- rejection rules.

Free strategy/code generation is explicitly disabled.

## Research Memory

Memory file:

- `reports/research/alpha_research_memory.json`

Current recorded trials:

| Run | Hypothesis | Family | Template | Status | Variants counted |
|---|---|---|---|---|---:|
| `p18d_alpha_hypothesis_runner_walk_forward_20260709` | `volatility_breakout` | `volatility_breakout` | `breakout_after_compression` | `REJECTED` | 5 |
| `p18e_alpha_runner_selected_smoke_20260709` | `long_trend` | `trend_momentum` | `regime_filtered_trend` | `REJECT_FAST` | 3 |

Rules enforced:

- each variant counts as a trial;
- rejected hypotheses remain visible;
- rejected current configs receive priority zero;
- no rejected hypothesis can be automatically rerun without new data or a new thesis.

## Scheduler Command

Initial VPS scheduler:

```bash
python -m autobot.v2.cli alpha-hypothesis-scheduler \
  --state-db /app/data/autobot_state.db \
  --data-paths /app/data/research/daily/ohlcv \
  --knowledge-base /app/docs/research/alpha_knowledge_base.json \
  --templates /app/docs/research/strategy_templates.json \
  --hypotheses /app/docs/research/alpha_hypotheses.json \
  --memory-path /app/reports/research/alpha_research_memory.json \
  --output-dir /app/reports/research/alpha_hypothesis_runner \
  --run-id p18e_alpha_hypothesis_scheduler_20260709_initial \
  --max-variants 5 \
  --max-symbols 6 \
  --max-runtime-seconds 300
```

## VPS Data Readiness

- Rows: 159,782
- Symbols: `AAVEEUR`, `ADAEUR`, `ATOMEUR`, `AVAXEUR`, `BCHEUR`, `BTCZEUR`, `DOTEUR`, `ETHZEUR`, `LINKEUR`, `LTCZEUR`, `SOLEUR`, `TRXEUR`, `XLMZEUR`, `XRPZEUR`
- Timeframes: `5m`, `15m`, `1h`
- Start: 2026-05-16T16:00:00+00:00
- End: 2026-07-09T00:15:00+00:00
- OHLCV ready: true
- Multi-symbol OHLCV ready: true
- Derivatives data: false
- Orderbook/depth data in scheduler readiness: false
- News data: false

## Initial Ranking

The scheduler selected `long_trend` automatically:

- hypothesis: `long_trend`
- template: `regime_filtered_trend`
- status: `RUNNABLE_SMOKE`
- priority_score: 130.0
- reason: data-ready, adapter-ready, no prior trials

`volatility_breakout` was not selected because P18D rejected the current config and memory blocks automatic rerun.

## Smoke Run Selected By AUTOBOT

Command:

```bash
python -m autobot.v2.cli alpha-hypothesis-runner \
  --hypothesis-id long_trend \
  --mode smoke \
  --state-db /app/data/autobot_state.db \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/alpha_hypothesis_runner \
  --run-id p18e_alpha_runner_selected_smoke_20260709 \
  --max-variants 3 \
  --max-symbols 6 \
  --max-runtime-seconds 120 \
  --templates /app/docs/research/strategy_templates.json \
  --memory-path /app/reports/research/alpha_research_memory.json
```

Smoke result:

- final_status: `REJECT_FAST`
- trades: 404
- PF net: 0.5992
- net PnL: -292.18 EUR
- expectancy: -0.7232 EUR/trade
- max drawdown: 294.09 EUR
- reasons:
  - `edge_net_not_positive`
  - `profit_factor_net_not_above_1`
  - `expectancy_net_not_positive`

No walk-forward was launched for `long_trend`, because the fast test failed.

## Scheduler After Smoke

After memory recorded the `long_trend` rejection, the scheduler selected no new hypothesis.

Top statuses after smoke:

| Hypothesis | Template | Status | Priority | Reason |
|---|---|---|---:|---|
| `volatility_breakout` | `breakout_after_compression` | `REJECTED_CURRENT_CONFIG` | 0.0 | rejected_current_config_requires_new_data |
| `funding_basis` | `funding_extreme_reversion` | `DATA_MISSING` | 0.0 | derivatives_data_missing, adapter_missing |
| `cross_momentum` | `leader_laggard_momentum` | `ADAPTER_MISSING` | 0.0 | adapter_missing |
| `liquidation_cascade` | `liquidation_recovery` | `DATA_MISSING` | 0.0 | derivatives_data_missing, orderbook_data_missing, adapter_missing |
| `long_trend` | `regime_filtered_trend` | `REJECTED_CURRENT_CONFIG` | 0.0 | rejected_current_config_requires_new_data |
| `cross_momentum` | `relative_strength_rotation` | `ADAPTER_MISSING` | 0.0 | adapter_missing |
| `mean_reversion__volatility_reversal_after_extension` | `volatility_reversal_after_extension` | `ADAPTER_MISSING` | 0.0 | adapter_missing |

## Generated Artifacts

- `reports/research/alpha_hypothesis_runner/p18e_alpha_hypothesis_scheduler_20260709_initial.json`
- `reports/research/alpha_hypothesis_runner/p18e_alpha_hypothesis_scheduler_20260709_initial.md`
- `reports/research/alpha_hypothesis_runner/p18e_alpha_runner_selected_smoke_20260709.json`
- `reports/research/alpha_hypothesis_runner/p18e_alpha_runner_selected_smoke_20260709.md`
- `reports/research/alpha_hypothesis_runner/p18e_alpha_hypothesis_scheduler_20260709_after_smoke.json`
- `reports/research/alpha_hypothesis_runner/p18e_alpha_hypothesis_scheduler_20260709_after_smoke.md`

## Security

- research-only
- no live
- no paper capital
- no promotion
- no shadow activation
- no runtime order path
- no UI change
- no sizing/leverage change
- no self-modifying code
- no free code generation
- no order
- grid remains no-go

## Recommendation P18F

AUTOBOT has exhausted currently runnable alpha templates with existing adapters:

- `volatility_breakout`: rejected by P18D walk-forward;
- `long_trend`: rejected by P18E smoke;
- funding/liquidation: data missing;
- cross-sectional/mean-reversion templates: adapter missing.

Recommended P18F: do not force more tests. Build the next small adapter only if it is template-backed and data-ready. The most reasonable next adapter candidate is `leader_laggard_momentum` or `relative_strength_rotation`, because OHLCV multi-symbol data exists and the blocker is adapter availability rather than missing derivatives/orderbook data.
