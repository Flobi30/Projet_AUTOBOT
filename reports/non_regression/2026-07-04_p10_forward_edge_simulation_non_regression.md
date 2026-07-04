# P10 Forward Edge Simulation Non-Regression - 2026-07-04

## Verdict

PASS_WITH_WARNINGS

P10 adds a research-only/read-only `forward_safe_net_edge` estimator and CLI simulation. It does not change live trading, paper capital, sizing, leverage, visible UI, grid runtime status, or strategy promotion.

## Scope

Modified files:

- `src/autobot/v2/paper/forward_edge_simulation.py`
- `src/autobot/v2/cli.py`
- `tests/paper/test_p6_score_and_confidence.py`

New CLI:

```bash
python -m autobot.v2.cli forward-edge-simulation --state-db data/autobot_state.db
```

## Anti-Lookahead Controls

- The estimator accepts only sanitized pre-entry inputs.
- Forbidden inputs include `exit`, `exit_price`, `closed_at`, `realized_pnl`, `gross_pnl`, `net_pnl`, `mfe_bps`, `mae_bps`, `outcome`, `post_trade_bucket`, `closing_leg`, and `closing_decision`.
- Raw ledger metadata may contain closing/outcome fields for evaluation, but the estimator input excludes them.
- Realized PnL is used only after scenario selection to evaluate retrospective performance.

## Safety

- `promotable=false` for all scenarios.
- `paper_capital_allowed=false` for all scenarios and segment policies.
- `live_allowed=false` for all scenarios and segment policies.
- Grid/legacy/unattributed rows remain excluded through runtime policy.
- `low` and `missing` buckets remain separate.
- `block_shadow_future`, `watch`, and `forward_edge_watch` are research-only statuses.

## Local Validation

Commands executed:

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m py_compile src/autobot/v2/paper/forward_edge_simulation.py src/autobot/v2/cli.py
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest -p no:cacheprovider tests/paper/test_p6_score_and_confidence.py -q
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest -p no:cacheprovider tests/paper/test_p6_score_and_confidence.py tests/paper/test_shadow_observation_sync.py tests/paper/test_loss_diagnostics.py tests/paper/test_official_performance.py -q
$env:PYTHONPATH='src'; python -m compileall -q src
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest -p no:cacheprovider tests/test_v2_cli.py tests/paper/test_p6_score_and_confidence.py tests/paper/test_shadow_observation_sync.py tests/paper/test_loss_diagnostics.py tests/paper/test_official_performance.py -q
```

Results:

- `test_p6_score_and_confidence.py`: 14 passed.
- Paper/diagnostic suite: 44 passed.
- CLI + paper suite: 71 passed.
- `compileall`: passed.

## Warnings

- The local worktree already contains tracked `.pyc` noise and historical untracked reports from earlier runs. These are not part of P10 and must not be staged.
- `cost_profile_fallback` is a configured pre-trade assumption, not a realized outcome. Reports expose the selected cost profile so it is auditable.
- If observations lack `expected_move_bps`, the forward estimator returns `insufficient_data` instead of inventing an expected move.

## Subagent Findings Integrated

- Avoided whole-metadata ingestion because loaded ledger metadata includes closing fields.
- Did not reuse P9 `expected_net_edge_adjusted_high` because it uses a realized net-edge proxy.
- Reused runtime policy blocking so grid/legacy rows cannot enter executable conclusions.

## VPS

Deployed and verified.

Deployment evidence:

- GitHub/VPS HEAD: `780354683e1bc4077fe35387686fa3bfb3ab3a05`
- Container: `autobot-v2 Up 4 minutes (healthy)` after rebuild/recreate.
- `/health`: `healthy`, `orchestrator=running`, `websocket=connected`, `instances=14`.
- Flags observed in container:
  - `PAPER_TRADING=true`
  - `LIVE_TRADING_CONFIRMATION=false`
  - `STRATEGY_ROUTER_LIVE_ENABLED=false`
  - `COLONY_AUTO_LIVE_PROMOTION=false`
  - `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset.
- Container compileall: passed.
- Critical log scan after deploy: no matching traceback/critical/live-order lines.

VPS P10 simulation:

```bash
docker exec -e PYTHONPATH=/app/src autobot-v2 python -m autobot.v2.cli forward-edge-simulation \
  --state-db /app/data/autobot_state.db \
  --run-id p10_vps_forward_edge \
  --output-dir /app/reports/paper/forward_edge_simulation
```

Output files:

- `reports/paper/forward_edge_simulation/p10_vps_forward_edge.json`
- `reports/paper/forward_edge_simulation/p10_vps_forward_edge.md`

Main results:

| Scenario | Trades | Net PnL | PF net | Confidence | Promotable |
|---|---:|---:|---:|---|---|
| all_scored | 2047 | -235.6364 | 0.5390 | rejected | false |
| opportunity_high_current | 137 | -9.0214 | 0.7637 | rejected | false |
| cost_aware_high | 4 | 1.2872 | 1.3077 | insufficient_data | false |
| forward_safe_net_edge_positive | 32 | -2.8638 | 0.9307 | insufficient_data | false |
| forward_safe_net_edge_top_quantile | 76 | -3.4739 | 0.9233 | rejected | false |
| forward_safe_net_edge_plus_score_high | 11 | 6.9552 | 1.6087 | insufficient_data | false |

Policy counts:

- `block_shadow_future`: 51
- `insufficient_data`: 37
- `observe`: 11
- `watch`: 9

Conclusion:

- P10 proves the estimator is wired and anti-lookahead guarded.
- The only positive result is `forward_safe_net_edge_plus_score_high`, but the sample is only 11 trades, so it remains `insufficient_data`.
- No paper capital, live, sizing, leverage, strategy promotion, or UI behavior was activated.
