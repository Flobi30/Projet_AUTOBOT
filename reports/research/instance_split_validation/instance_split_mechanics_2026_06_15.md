# Instance Split Validation - instance_split_mechanics_2026_06_15

Verdict: **PASS**
Generated at: `2026-06-15T17:12:34.301619+00:00`

## Mechanical checks

- PASS: `first_split_policy_passed`
- PASS: `paper_mode_only`
- PASS: `live_promotion_disabled`
- PASS: `no_order_path`
- PASS: `capital_conserved_at_split`
- PASS: `child_state_changes_independently`
- PASS: `lineage_persisted`
- PASS: `second_split_blocked_for_lifetime`

## Result

- Parent: `{'instance_id': 'paper-parent-validated', 'initial_capital_eur': 4000.0, 'current_capital_eur': 3000.0}`
- Child: `{'instance_id': 'paper-parent-validated-child-1', 'initial_capital_eur': 1000.0, 'current_capital_eur': 1011.99576}`
- First decision: `{'allowed_to_plan': True, 'executor_enabled': True, 'executable_now': True, 'status': 'executable_paper_only', 'reason': 'split_policy_passed_and_executor_enabled', 'blockers': [], 'planned_child_capital_eur': 1000.0, 'parent_capital_after_eur': 3000.0, 'live_promotion_allowed': False, 'config': {'executor_enabled': True, 'paper_mode_only': True, 'max_splits_per_parent_lifetime': 1, 'min_parent_capital_eur': 2000.0, 'child_capital_pct': 25.0, 'min_child_capital_eur': 400.0, 'min_net_pnl_eur': 0.0, 'min_profit_factor': 1.25, 'min_trade_count': 100, 'min_validation_days': 7, 'max_drawdown_pct': 12.0, 'min_strategy_scorecard': 75.0, 'required_strategy_statuses': ['paper_validated'], 'blocked_failure_modes': ['weak_mfe_below_cost'], 'feature_flag': 'ENABLE_INSTANCE_SPLIT_EXECUTOR'}, 'evidence': {'parent_instance_id': 'paper-parent-validated', 'parent_capital_eur': 4000.0, 'parent_available_eur': 3000.0, 'parent_lifetime_split_count': 0, 'lineage_verified': True, 'paper_mode': True, 'strategy_id': 'trend_momentum', 'strategy_status': 'paper_validated', 'net_pnl_eur': 250.0, 'profit_factor': 1.45, 'trade_count': 180, 'validation_days': 14, 'max_drawdown_pct': 6.0, 'strategy_scorecard': 84.0, 'dominant_failure_mode': 'healthy', 'official_paper_net_pnl_eur': 220.0, 'live_promotion_allowed': False, 'metadata': {}}}`
- Second decision: `{'allowed_to_plan': False, 'executor_enabled': True, 'executable_now': False, 'status': 'blocked', 'reason': 'parent_already_split', 'blockers': ['parent_already_split'], 'planned_child_capital_eur': 1000.0, 'parent_capital_after_eur': 3000.0, 'live_promotion_allowed': False, 'config': {'executor_enabled': True, 'paper_mode_only': True, 'max_splits_per_parent_lifetime': 1, 'min_parent_capital_eur': 2000.0, 'child_capital_pct': 25.0, 'min_child_capital_eur': 400.0, 'min_net_pnl_eur': 0.0, 'min_profit_factor': 1.25, 'min_trade_count': 100, 'min_validation_days': 7, 'max_drawdown_pct': 12.0, 'min_strategy_scorecard': 75.0, 'required_strategy_statuses': ['paper_validated'], 'blocked_failure_modes': ['weak_mfe_below_cost'], 'feature_flag': 'ENABLE_INSTANCE_SPLIT_EXECUTOR'}, 'evidence': {'parent_instance_id': 'paper-parent-validated', 'parent_capital_eur': 4000.0, 'parent_available_eur': 3000.0, 'parent_lifetime_split_count': 1, 'lineage_verified': True, 'paper_mode': True, 'strategy_id': 'trend_momentum', 'strategy_status': 'paper_validated', 'net_pnl_eur': 250.0, 'profit_factor': 1.45, 'trade_count': 180, 'validation_days': 14, 'max_drawdown_pct': 6.0, 'strategy_scorecard': 84.0, 'dominant_failure_mode': 'healthy', 'official_paper_net_pnl_eur': 220.0, 'live_promotion_allowed': False, 'metadata': {}}}`

## Safety

- Research-only mechanics validation.
- No AUTOBOT runtime service is started.
- No Kraken endpoint or credential is used.
- No paper or live order is created.
- No live promotion permission is granted.
