# Spin-Off Duplication Safety - 2026-06-06

Generated evidence: `reports/research/spinoff_2026-06-06/spinoff_duplication_safety_2026-06-06.md`

## Verdict

Duplication must remain blocked.

The new split policy/planner is read-only and feature-flagged off by default:

- `ENABLE_INSTANCE_SPLIT_EXECUTOR=false` by default.
- Planner creates no child.
- Planner creates no paper order.
- Planner creates no live order.
- `live_promotion_allowed` is always false.

## Checks

| Check | Result |
| --- | --- |
| Parent can split more than once? | New policy blocks if persistent lifetime count >= 1. Old runtime still needs wiring to this policy. |
| `instance_lineage` consulted? | New planner reads persistent `instance_lineage`. |
| Split requires only PF/capital? | New policy requires PnL, official paper PnL, PF, trade count, validation days, drawdown, scorecard and strategy status. |
| Strategy `rejected` / `research_only` blocked? | yes |
| `weak_mfe_below_cost` blocked? | yes |
| Negative official paper PnL blocked? | yes |
| Paper-only? | yes |
| Live child possible by accident? | no in new policy/planner |

## Evidence Run

Input evidence represented current grid failure:

- Net PnL after fees: -333.55 EUR.
- Profit factor: 0.4.
- Strategy status: `research_only`.
- Strategy scorecard: 25.
- Dominant failure mode: `weak_mfe_below_cost`.

Decision:

- Status: `blocked`.
- Blockers: `net_pnl_not_positive_after_costs`, `official_paper_net_pnl_not_positive`, `profit_factor_below_threshold`, `strategy_scorecard_below_threshold`, `strategy_status_not_validated`, `blocked_failure_mode:weak_mfe_below_cost`.

## Next Step

Before any duplication executor is ever enabled, route old runtime `check_spin_off` through `InstanceSplitPolicy` and verify persistent one-split-per-parent lifetime behavior.
