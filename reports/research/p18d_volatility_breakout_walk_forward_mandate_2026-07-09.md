# P18D - Volatility Breakout Walk-Forward + Risk Mandate

Date: 2026-07-09  
Commit: `2a2b77ace3964db0a52d0700c9059c4eb859c88a`  
Mode: research-only

## Scope

P18D used the Alpha Hypothesis Runner to validate `volatility_breakout` through the bounded research pipeline. No live, paper capital, promotion, shadow activation, sizing, leverage, UI, paper executor, router runtime, or order path was changed.

## Commands

```bash
python -m autobot.v2.cli alpha-hypothesis-runner \
  --hypothesis-id volatility_breakout \
  --mode walk_forward \
  --state-db /app/data/autobot_state.db \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/alpha_hypothesis_runner \
  --run-id p18d_alpha_hypothesis_runner_walk_forward_20260709 \
  --max-variants 5 \
  --max-symbols 6 \
  --max-runtime-seconds 300 \
  --commit 2a2b77ace3964db0a52d0700c9059c4eb859c88a
```

```bash
python -m autobot.v2.cli strategy-autonomy-check \
  --strategy-id volatility_breakout \
  --state-db /app/data/autobot_state.db \
  --mandates /app/docs/research/strategy_risk_mandates.json
```

## Data Used

- Path: `/app/data/research/daily/ohlcv`
- Period covered in diagnostics: 2026-06-14 to 2026-07-08
- Symbols: `ADAEUR`, `BCHEUR`, `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `XRPZEUR`
- Timeframes: `5m`, `15m`, `1h`
- Raw rows: 343,917
- Deduped rows: 68,478
- Duplicate rows detected before dedupe: 275,439
- Gaps: 0

## Alpha Runner Gates

| Gate | Status | Passed | Runtime s | Reasons |
|---|---:|---:|---:|---|
| DATA_CHECK | KEEP_RESEARCH | true | 26.619 | data_ready |
| FAST_NET_EDGE_TEST | KEEP_RESEARCH | true | 53.286 | positive_smoke_requires_walk_forward_before_shadow, no_shadow_or_paper_allowed |
| WALK_FORWARD | REJECT | false | 80.097 | drawdown_above_12_pct_proxy, majority_folds_not_positive, positive_pnl_concentrated_in_one_symbol, fails_without_bcheur, fails_without_bcheur_adaeur |

The runner stopped after `WALK_FORWARD`. It did not launch stress or Monte-Carlo because the walk-forward gate failed.

## Walk-Forward Result

Overall primary scenario:

- Trades: 206
- Net PF: 1.0248
- Net PnL: +10.99 EUR
- Net expectancy: +0.0534 EUR/trade
- Win rate: 36.89%
- Max drawdown: 253.57 EUR proxy in runner gate
- No-trade baseline: 0.00 EUR
- Verdict: REJECT

Fold diagnostics from the strict walk-forward report:

| Fold | Test period | Trades | PF net | Net PnL EUR | Expectancy EUR | Max DD EUR | Win rate |
|---|---|---:|---:|---:|---:|---:|---:|
| fold_1 | 2026-06-15 to 2026-06-17 | 47 | 0.2526 | -126.19 | -2.6848 | 159.16 | 8.5% |
| fold_2 | 2026-06-20 to 2026-06-22 | 5 | 0.0000 | -17.46 | -3.4923 | 17.46 | 0.0% |
| fold_3 | 2026-06-24 to 2026-06-27 | 16 | 0.1066 | -36.78 | -2.2986 | 36.78 | 25.0% |
| fold_4 | 2026-06-29 to 2026-07-02 | 23 | 2.3174 | +41.39 | +1.7996 | 31.42 | 56.5% |
| fold_5 | 2026-07-04 to 2026-07-06 | 34 | 0.0872 | -101.56 | -2.9871 | 101.56 | 11.8% |

Positive folds: 1/5.

## Symbol Concentration

| Symbol | Trades | PF net | Net PnL EUR | Expectancy EUR | Max DD EUR | Win rate |
|---|---:|---:|---:|---:|---:|---:|
| ADAEUR | 59 | 1.1205 | +16.86 | +0.2858 | 79.75 | 39.0% |
| BCHEUR | 51 | 1.9602 | +93.77 | +1.8386 | 74.66 | 45.1% |
| ETHZEUR | 23 | 0.9241 | -2.76 | -0.1201 | 32.34 | 43.5% |
| SOLEUR | 43 | 0.3716 | -64.44 | -1.4986 | 84.85 | 25.6% |
| XRPZEUR | 30 | 0.5186 | -32.44 | -1.0812 | 46.57 | 30.0% |

Concentration diagnostics:

- Top positive symbol: `BCHEUR`
- Top positive symbol share: 84.76% of positive symbol PnL
- Without BCHEUR: 155 trades, PF 0.7609, net PnL -82.78 EUR
- Without BCHEUR + ADAEUR: 96 trades, PF 0.5170, net PnL -99.64 EUR
- Only BCHEUR + ADAEUR: 110 trades, PF 1.4658, net PnL +110.63 EUR

These exclusions are diagnostic only. They do not create a BCHEUR-only or ADAEUR-only strategy.

## Risk Mandate Status

Strategy: `volatility_breakout`  
Mandate: `research_volatility_breakout_default`  
Mode allowed: `research`  
Capital max: 0.00 EUR  
Paper capital allowed: false  
Live allowed: false  
Promotable: false

`strategy-autonomy-check` final decision: `BLOCK`

Passed checks:

- daily_loss_within_limit
- data_fresh
- drawdown_within_limit
- fees_within_limit
- notional_within_limit
- slippage_within_limit
- spread_within_limit
- symbol_allowed
- symbol_exposure_within_limit
- timeframe_allowed
- total_exposure_within_limit

Failed checks:

- edge_to_cost_ratio
- order_type_allowed
- orders_per_minute_within_limit
- trades_per_day_within_limit

Static research-only blockers:

- mode_is_research_only
- capital_max_eur_is_zero
- paper_capital_allowed_false
- runtime_orders_not_allowed

Auto-kill/downgrade health decision: `ALLOW`, with `health` in passed checks and no blockers. This is only a read-only risk-mandate report and is not connected to runtime execution.

## Verdict

Final verdict: `REJECT`.

Although the aggregate PF is slightly above 1, the signal fails the strict walk-forward decision rules:

- only 1/5 folds is positive;
- drawdown is too high relative to the intended risk envelope;
- positive PnL is concentrated in BCHEUR;
- the result becomes negative without BCHEUR;
- the result becomes strongly negative without BCHEUR + ADAEUR.

No stress/Monte-Carlo stage was launched because walk-forward failed.

## Safety Confirmation

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset/false
- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- no live order
- no paper capital
- no promotion
- no runtime order path touched
- grid remains blocked/no-go

## Recommendation P18E

Do not continue volatility_breakout toward shadow or paper. Keep it as a rejected research hypothesis unless future data produces a materially different, fold-stable result through the same Alpha Hypothesis Runner.

Recommended P18E direction: improve the Alpha Hypothesis Runner reporting contract so fold metrics and concentration details are surfaced directly in the runner JSON/Markdown, then let the runner evaluate the next hypothesis from `alpha_hypotheses.json` under the same gates.
