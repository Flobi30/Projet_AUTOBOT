# Instance Split Plan - spinoff_duplication_safety_2026-06-06

Generated at: `2026-06-06T16:50:26.670784+00:00`
State DB: `data\vps_autobot_state_2026-06-04_2026-06-04_121159.db`

## Decisions

| Parent | Status | Plan Allowed | Executable | Child Capital | Parent After | Blockers |
| --- | --- | --- | --- | ---: | ---: | --- |
| autobot_mother | blocked | no | no | 1000.00 | 3000.00 | net_pnl_not_positive_after_costs, official_paper_net_pnl_not_positive, profit_factor_below_threshold, strategy_scorecard_below_threshold, strategy_status_not_validated, blocked_failure_mode:weak_mfe_below_cost |

## Safety

- Read-only split planning only.
- ENABLE_INSTANCE_SPLIT_EXECUTOR defaults to false.
- No instance is created by this planner.
- No paper or live order is created.
- No live trading permission is granted.
