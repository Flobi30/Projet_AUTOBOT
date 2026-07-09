# P18E Alpha Hypothesis Scheduler - p18f_scheduler_after_memory_backfill

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
| 1 | `volatility_breakout` | `breakout_after_compression` | `REJECTED_CURRENT_CONFIG` | 0.00 | rejected_current_config_requires_new_data | wait_for_new_data_or_new_thesis |
| 2 | `funding_basis` | `funding_extreme_reversion` | `DATA_MISSING` | 0.00 | derivatives_data_missing, adapter_missing | collect_required_data_or_mark_not_suitable |
| 3 | `cross_momentum` | `leader_laggard_momentum` | `ADAPTER_MISSING` | 0.00 | adapter_missing | write_adapter_before_testing |
| 4 | `liquidation_cascade` | `liquidation_recovery` | `DATA_MISSING` | 0.00 | derivatives_data_missing, orderbook_data_missing, adapter_missing | collect_required_data_or_mark_not_suitable |
| 5 | `long_trend` | `regime_filtered_trend` | `REJECTED_CURRENT_CONFIG` | 0.00 | rejected_current_config_requires_new_data | wait_for_new_data_or_new_thesis |
| 6 | `cross_momentum` | `relative_strength_rotation` | `ADAPTER_MISSING` | 0.00 | adapter_missing | write_adapter_before_testing |
| 7 | `mean_reversion__volatility_reversal_after_extension` | `volatility_reversal_after_extension` | `ADAPTER_MISSING` | 0.00 | adapter_missing | write_adapter_before_testing |

## Selected Next Hypothesis

- No runnable smoke hypothesis. Build missing data/adapters first.

## Adapter Backlog

| Rank | Adapter | Template | Family | Data ready | Priority | Reason |
|---:|---|---|---|---:|---:|---|
| 1 | `leader_laggard_momentum_adapter` | `leader_laggard_momentum` | `cross_sectional_momentum` | `True` | 112.25 | data-ready, low-complexity, cpu-L, reuse=0.95 |
| 2 | `relative_strength_rotation_adapter` | `relative_strength_rotation` | `cross_sectional_momentum` | `True` | 110.50 | data-ready, low-complexity, cpu-L, reuse=0.90 |
| 3 | `volatility_reversal_after_extension_adapter` | `volatility_reversal_after_extension` | `mean_reversion` | `True` | 75.50 | data-ready, low-complexity, cpu-L, reuse=0.50, penalized by rejected related config |
| 4 | `funding_extreme_reversion_adapter` | `funding_extreme_reversion` | `funding_basis` | `False` | 15.00 | data missing: derivatives_data_missing |
| 5 | `liquidation_recovery_adapter` | `liquidation_recovery` | `liquidation_cascade` | `False` | 10.00 | data missing: derivatives_data_missing, orderbook_data_missing |

## Top Adapter Recommendation

- Adapter: `leader_laggard_momentum_adapter`
- Template: `leader_laggard_momentum`
- Priority: `112.25`
- Reason: data-ready, low-complexity, cpu-L, reuse=0.95

## Memory Backfill

- `before_count`: `10`
- `after_count`: `10`
- `added_count`: `0`
- `updated_count`: `1`
- `imported_run_ids`: `['p17_high_conviction_history_20260709', 'p18b_volatility_breakout_smoke_20260709', 'p18d_alpha_hypothesis_runner_walk_forward_20260709', 'p18e_alpha_runner_selected_smoke_20260709', 'strategy_edge_review_20260629_trend_momentum', 'strategy_edge_review_20260629_mean_reversion', 'strategy_edge_review_20260629_relative_value', 'strategy_edge_review_20260629_grid', 'relative_value_20260622', 'strategy_hypotheses_grid_no_go']`
- `missing_sources`: `[]`

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
