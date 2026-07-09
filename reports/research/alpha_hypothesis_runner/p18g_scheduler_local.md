# P18E Alpha Hypothesis Scheduler - p18g_scheduler_local

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no shadow activation.
- No runtime order path, no UI, no sizing/leverage change.
- No self-modifying code and no free strategy code generation.

## Data Readiness

- `symbols`: `('ADAEUR', 'AVAXEUR', 'DOTEUR', 'LINKEUR', 'SOLEUR', 'TRXEUR', 'XRPZEUR')`
- `timeframes`: `('15m', '1h', '5m')`
- `row_count`: `15141`
- `duplicate_count`: `0`
- `gap_count`: `0`
- `start_at`: `2026-05-09T08:00:00+00:00`
- `end_at`: `2026-06-08T08:25:00+00:00`
- `has_spot_ohlcv`: `True`
- `has_multi_symbol_ohlcv`: `True`
- `has_5m`: `True`
- `has_15m`: `True`
- `has_1h`: `True`
- `has_orderbook`: `False`
- `has_derivatives`: `False`
- `has_news`: `False`

## Candidates

| Rank | Hypothesis | Template | Status | Priority | Reason | Next action |
|---:|---|---|---|---:|---|---|
| 1 | `cross_momentum` | `leader_laggard_momentum` | `RUNNABLE_SMOKE` | 130.00 | data-ready, adapter-ready, family_trials=0, template_trials=0 | run_alpha_hypothesis_runner_smoke |
| 2 | `cross_momentum` | `relative_strength_rotation` | `RUNNABLE_SMOKE` | 130.00 | data-ready, adapter-ready, family_trials=0, template_trials=0 | run_alpha_hypothesis_runner_smoke |
| 3 | `volatility_breakout` | `breakout_after_compression` | `REJECTED_CURRENT_CONFIG` | 0.00 | rejected_current_config_requires_new_data | wait_for_new_data_or_new_thesis |
| 4 | `funding_basis` | `funding_extreme_reversion` | `DATA_MISSING` | 0.00 | derivatives_data_missing, adapter_missing | collect_required_data_or_mark_not_suitable |
| 5 | `liquidation_cascade` | `liquidation_recovery` | `DATA_MISSING` | 0.00 | derivatives_data_missing, orderbook_data_missing, adapter_missing | collect_required_data_or_mark_not_suitable |
| 6 | `long_trend` | `regime_filtered_trend` | `REJECTED_CURRENT_CONFIG` | 0.00 | rejected_current_config_requires_new_data | wait_for_new_data_or_new_thesis |
| 7 | `mean_reversion__volatility_reversal_after_extension` | `volatility_reversal_after_extension` | `ADAPTER_MISSING` | 0.00 | adapter_missing | write_adapter_before_testing |

## Selected Next Hypothesis

- Hypothesis: `cross_momentum`
- Template: `leader_laggard_momentum`
- Command: `python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id cross_momentum --mode smoke --state-db data\autobot_state.db --data-paths data\research\daily\ohlcv --output-dir reports\research\alpha_hypothesis_runner --max-variants 3 --max-symbols 6 --max-runtime-seconds 120 --template-id leader_laggard_momentum`

## Adapter Backlog

| Rank | Adapter | Template | Family | Data ready | Priority | Reason |
|---:|---|---|---|---:|---:|---|
| 1 | `volatility_reversal_after_extension_adapter` | `volatility_reversal_after_extension` | `mean_reversion` | `True` | 75.50 | data-ready, low-complexity, cpu-L, reuse=0.50, penalized by rejected related config |
| 2 | `funding_extreme_reversion_adapter` | `funding_extreme_reversion` | `funding_basis` | `False` | 15.00 | data missing: derivatives_data_missing |
| 3 | `liquidation_recovery_adapter` | `liquidation_recovery` | `liquidation_cascade` | `False` | 10.00 | data missing: derivatives_data_missing, orderbook_data_missing |

## Top Adapter Recommendation

- Adapter: `volatility_reversal_after_extension_adapter`
- Template: `volatility_reversal_after_extension`
- Priority: `75.50`
- Reason: data-ready, low-complexity, cpu-L, reuse=0.50, penalized by rejected related config

## Trial Counts

- By family: `{'volatility_breakout': 10, 'trend_momentum': 4, 'mean_reversion': 1, 'relative_value': 3, 'grid': 2}`
- By template: `{'breakout_after_compression': 10, 'regime_filtered_trend': 4, 'volatility_reversal_after_extension': 1, 'relative_value_pair_spread': 3, 'dynamic_grid': 2}`

## Safety

- Research-only scheduler.
- No free code generation.
- No runtime order path, paper capital, live activation, promotion, sizing, leverage, or UI change.
- Rejected hypotheses receive zero priority until new data or a new thesis is recorded.
- paper_capital_allowed: `False`
- live_allowed: `False`
- promotable: `False`
