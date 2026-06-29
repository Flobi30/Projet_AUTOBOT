# Strategy Edge Review - 2026-06-29

- run_id: `strategy_edge_2026_06_29_vps`
- generated_at: `2026-06-29T16:54:17.346280+00:00`
- scope: research_only
- orders_created: false
- paper/live runtime modified: false

## Strategy triage

| Strategy | Requested status | Capital status | Observed status | PF | PnL EUR | Trades | Folds | Gate | Blockers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| high_conviction_swing | active_research_keep_testing | capital_research_limited | active_research | 1.0984 | 7.1233 | 45 | 2/8 | D | insufficient_trade_count_for_candidate_review, profit_factor_below_candidate_threshold, insufficient_positive_fold_ratio, single_symbol_concentration_above_limit |
| trend_momentum | research_signal_only | no_capital_redesign_required | research_signal_only | - | - | 0 | 0/0 | E | insufficient_trade_count_for_candidate_review, profit_factor_below_candidate_threshold, redesign_required_before_capital |
| mean_reversion | research_signal_only | no_capital_cost_aware_review_required | research_signal_only | - | - | 0 | 0/0 | E | insufficient_trade_count_for_candidate_review, profit_factor_below_candidate_threshold, cost_aware_review_required_before_capital |
| relative_value | no_go | no_capital | no_go | - | - | 0 | 0/0 | E | strategy_currently_no_go_or_archived |
| grid | archived | no_go | archived | - | - | 0 | 0/0 | E | strategy_currently_no_go_or_archived |

## High Conviction summary

- net_pnl_eur: `7.1233`
- profit_factor: `1.0984`
- trades: `45`
- folds: `2/8`
- largest_positive_symbol_share: `0.6795`
- pair_quarantine_candidates: `AVAXEUR, XLMZEUR`

## Safety

- live_promotion_allowed: false
- official_paper_modified: false
- child_instance_created: false
