# P18E Alpha Hypothesis Scheduler - p18e_alpha_hypothesis_scheduler_20260709_after_smoke

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no shadow activation.
- No runtime order path, no UI, no sizing/leverage change.
- No self-modifying code and no free strategy code generation.

## Data Readiness

- `symbols`: `('AAVEEUR', 'ADAEUR', 'ATOMEUR', 'AVAXEUR', 'BCHEUR', 'BTCZEUR', 'DOTEUR', 'ETHZEUR', 'LINKEUR', 'LTCZEUR', 'SOLEUR', 'TRXEUR', 'XLMZEUR', 'XRPZEUR')`
- `timeframes`: `('15m', '1h', '5m')`
- `row_count`: `159782`
- `duplicate_count`: `632597`
- `gap_count`: `0`
- `start_at`: `2026-05-16T16:00:00+00:00`
- `end_at`: `2026-07-09T00:15:00+00:00`
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

## Trial Counts

- By family: `{'volatility_breakout': 5, 'trend_momentum': 3}`
- By template: `{'breakout_after_compression': 5, 'regime_filtered_trend': 3}`

## Safety

- Research-only scheduler.
- No free code generation.
- No runtime order path, paper capital, live activation, promotion, sizing, leverage, or UI change.
- Rejected hypotheses receive zero priority until new data or a new thesis is recorded.
- paper_capital_allowed: `False`
- live_allowed: `False`
- promotable: `False`
