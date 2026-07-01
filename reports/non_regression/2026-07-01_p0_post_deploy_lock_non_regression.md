# P0 Post-Deploy Lock Non-Regression - 2026-07-01

## Verdict

PASS_WITH_WARNINGS pending final VPS rebuild verification.

## Scope

This lock keeps the P0 strategy-registry / paper-ledger patch intact and adds
one missing guard: legacy closing trades written before P0 without a
`strategy_id` remain auditable historical records, but they are excluded from
official post-P0 strategy metrics by default.

No UI-visible design was changed. No strategy was added. No live flag, sizing
rule, risk rule, or runtime promotion flag was changed.

## Commit Lineage To Clarify

- `47213731c5ce37359974c3f827d316dd83957ee8` was the P0 code deployment that
  enforced mandatory strategy identity through the paper path.
- `7962769908ea5efcbbe2d2afcaf0950f3b152737` was a later registry/report
  alignment commit on GitHub and VPS. It did not rebuild the container and did
  not change the P0 runtime code path.
- This post-deploy lock supersedes both for runtime code. After deployment,
  GitHub `master`, VPS `/opt/Projet_AUTOBOT`, and the rebuilt container source
  must be checked against the final post-lock commit.

## Files Changed

- `src/autobot/v2/strategy_runtime_policy.py`
- `src/autobot/v2/persistence.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `tests/test_pf_phase2.py`
- `tests/paper/test_paper_ledger_loader.py`
- `tests/test_strategy_validation_registry.py`
- `reports/non_regression/2026-07-01_p0_post_deploy_lock_non_regression.md`

## Legacy Trade Handling

- New reserved audit id: `legacy_unattributed`.
- `legacy_unattributed` is not a valid official paper `strategy_id`.
- `StatePersistence.append_trade_ledger()` still rejects missing strategy ids
  and retired Grid aliases through `official_paper_strategy_block_reason()`.
- `get_trade_ledger_metrics_by_strategy()` excludes missing/blank `strategy_id`
  rows by default.
- `get_trade_ledger_metrics_by_strategy(include_legacy=True)` exposes those
  rows only for audit under `legacy_unattributed`.
- `paper_trades.db` FIFO legacy loader now labels old unattributed fills as
  `legacy_unattributed`.

## Official Metrics Impact

Legacy unattributed trades cannot be used for:

- official PF by strategy;
- official expectancy by strategy;
- promotion gate evidence;
- strategy/pair allocation evidence.

Historical global paper PnL remains an audit/history concept and is not treated
as strategy-validating evidence.

## Tests

Commands run locally:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_pf_phase2.py tests/paper/test_paper_ledger_loader.py tests/test_strategy_validation_registry.py -q
python -m compileall -q src
```

Results:

- Focused P0 lock suite: 33 passed.
- `compileall`: PASS.

Added/covered assertions:

- A directly inserted legacy closing row without `strategy_id` is excluded from
  official `get_trade_ledger_metrics_by_strategy()` output.
- The same row appears only when `include_legacy=True`, under
  `legacy_unattributed`.
- `legacy_unattributed` is blocked by runtime policy and cannot become an
  official paper strategy id.
- Legacy `paper_trades.db` FIFO fills are labelled `legacy_unattributed`.

## Live Safety Confirmation

- No live flag changed.
- No Kraken order created.
- No paper/live runtime strategy promoted.
- No sizing/risk rule changed.
- No duplication/spin-off flag changed.
- Grid remains retired/research-only.

## Residual Warnings

- A committed report cannot safely embed its own final Git SHA without changing
  that SHA. The final deployed SHA must be taken from the post-deployment
  `git rev-parse HEAD` checks and reported alongside this file.
- Historical global PnL views may still include old historical rows for audit,
  but official strategy metrics exclude them by default.
