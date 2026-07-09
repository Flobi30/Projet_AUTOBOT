# P18F - Research Memory Backfill + Adapter Backlog Prioritizer

Date: 2026-07-09  
Mode: research-only

## Objective

P18F prevents AUTOBOT from forgetting rejected or weak historical results before scheduling new alpha tests. It backfills `reports/research/alpha_research_memory.json` from existing reports, then ranks missing adapters without building any adapter or activating trading.

## Scope And Safety

- No live trading.
- No paper capital.
- No promotion.
- No shadow activation.
- No runtime order path touched.
- No UI, sizing, leverage or strategy activation change.
- Grid remains no-go/runtime-disabled.

## Files Changed

- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`
- `reports/research/alpha_research_memory.json`
- `reports/research/alpha_hypothesis_runner/p18f_scheduler_after_memory_backfill.json`
- `reports/research/alpha_hypothesis_runner/p18f_scheduler_after_memory_backfill.md`

## Memory Backfill

Source reports imported:

| Run | Hypothesis | Status | Key metric | Source |
|---|---|---|---|---|
| `p17_high_conviction_history_20260709` | `high_conviction_swing` | `REJECTED` | PF net 0.8772, net PnL -16.53 EUR | `reports/research/p17_high_conviction_historical_validation_2026-07-09.md` |
| `p18b_volatility_breakout_smoke_20260709` | `volatility_breakout` | `KEEP_RESEARCH` | PF net 1.0248, net PnL +10.99 EUR | `reports/research/alpha_smoke/p18b_alpha_smoke_20260709.json` |
| `p18d_alpha_hypothesis_runner_walk_forward_20260709` | `volatility_breakout` | `REJECTED` | PF net 1.0248 but failed folds/concentration/drawdown | `reports/research/alpha_hypothesis_runner/p18d_alpha_hypothesis_runner_walk_forward_20260709.json` |
| `p18e_alpha_runner_selected_smoke_20260709` | `long_trend` | `REJECT_FAST` | PF net 0.5992, net PnL -292.18 EUR | `reports/research/alpha_hypothesis_runner/p18e_alpha_runner_selected_smoke_20260709.json` |
| `strategy_edge_review_20260629_trend_momentum` | `trend_momentum` | `BENCHMARK_REJECTED` | benchmark/no-capital | `reports/research/strategy_edge_improvement_2026_06_29.json` |
| `strategy_edge_review_20260629_mean_reversion` | `mean_reversion` | `BENCHMARK_REJECTED` | benchmark/no-capital | `reports/research/strategy_edge_improvement_2026_06_29.json` |
| `relative_value_20260622` | `relative_value` | `NO_GO` | PF net 0.2835, net PnL -14.70 EUR | `reports/research/relative_value_2026_06_22/relative_value_2026_06_22.json` |
| `strategy_hypotheses_grid_no_go` | `grid` | `RETIRED_FROM_EXECUTION` | grid archived/no-go | `docs/research/strategy_hypotheses.json` |

Backfill result:

- Memory records after backfill: 10.
- Missing source reports: 0.
- No duplicate `run_id` records.
- Every imported record has `paper_capital_allowed=false`, `live_allowed=false`, `promotable=false`.

## Scheduler Result

Command:

```bash
python -m autobot.v2.cli alpha-hypothesis-scheduler \
  --state-db data/autobot_state.db \
  --data-paths data/research/daily/ohlcv \
  --knowledge-base docs/research/alpha_knowledge_base.json \
  --templates docs/research/strategy_templates.json \
  --hypotheses docs/research/alpha_hypotheses.json \
  --memory-path reports/research/alpha_research_memory.json \
  --output-dir reports/research/alpha_hypothesis_runner \
  --run-id p18f_scheduler_after_memory_backfill \
  --max-variants 5 \
  --max-symbols 6 \
  --max-runtime-seconds 300
```

Selected hypothesis: none.

Reason:

- `volatility_breakout` is rejected by P18D and cannot rerun without new data or a materially new thesis.
- `long_trend` is rejected by P18E and cannot be treated as “no prior trial”.
- funding/liquidation hypotheses are data-missing.
- cross-sectional hypotheses are data-ready but adapter-missing.

## Adapter Backlog

| Rank | Adapter | Template | Family | Data ready | Priority | Reason |
|---:|---|---|---|---:|---:|---|
| 1 | `leader_laggard_momentum_adapter` | `leader_laggard_momentum` | `cross_sectional_momentum` | true | 112.25 | OHLCV-ready, low complexity, low CPU, high reuse |
| 2 | `relative_strength_rotation_adapter` | `relative_strength_rotation` | `cross_sectional_momentum` | true | 110.50 | OHLCV-ready, low complexity, low CPU, high reuse |
| 3 | `volatility_reversal_after_extension_adapter` | `volatility_reversal_after_extension` | `mean_reversion` | true | 75.50 | data-ready but penalized by rejected mean-reversion evidence |
| 4 | `funding_extreme_reversion_adapter` | `funding_extreme_reversion` | `funding_basis` | false | 15.00 | derivatives data missing |
| 5 | `liquidation_recovery_adapter` | `liquidation_recovery` | `liquidation_cascade` | false | 10.00 | derivatives and orderbook/depth data missing |

Top recommended adapter for P18G: `leader_laggard_momentum_adapter`.

Reason: it is spot-only, OHLCV-only, data-ready on the current VPS dataset, low CPU, bounded by the template, and reusable for the broader cross-sectional momentum family. This is only a recommendation to build an adapter next; P18F did not build it.

## Tests

Commands run:

```bash
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py tests\research\test_archived_grid_defaults.py tests\test_grid_health_gate.py tests\test_grid_setup_optimizer_gate.py tests\test_strategy_validation_registry.py tests\test_strategy_governance.py -q
```

Results:

- compileall: OK.
- Scheduler tests: 12 passed.
- CLI/scheduler tests: 39 passed.
- Paper/governance/grid-focused regression: 69 passed.

## Recommendation P18G

Build only one small research-only adapter next: `leader_laggard_momentum_adapter`.

Do not rerun `volatility_breakout`, `long_trend`, `trend_momentum`, `mean_reversion`, `relative_value`, or `grid` as if they had no history. They require new data, new thesis, or redesign before another bounded test.
