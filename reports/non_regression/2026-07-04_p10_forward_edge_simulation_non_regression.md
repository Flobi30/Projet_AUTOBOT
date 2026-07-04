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

Pending deployment and post-deploy read-only verification.

