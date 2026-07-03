# P6 Non-Regression - DB Reliability, Score Filter, Paper Confidence

Date: 2026-07-03

## Verdict

PASS_WITH_WARNINGS

P6 adds research-only diagnostics and SQLite write hardening. No live trading,
paper capital, sizing, leverage, strategy promotion, UI, or runtime trading flag
was changed.

## Files Modified

- `src/autobot/v2/persistence.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/db_integrity.py`
- `src/autobot/v2/paper/score_filter_simulation.py`
- `src/autobot/v2/paper/paper_confidence.py`
- `src/autobot/v2/cli.py`
- `docs/research/STRATEGY_ACCEPTANCE_CRITERIA.md`
- `tests/test_persistence_db_reliability.py`
- `tests/paper/test_p6_score_and_confidence.py`
- `tests/test_v2_cli.py`

## What Changed

- Runtime SQLite write paths for trade ledger, decision ledger, market samples
  and market-sample purges now use bounded busy retry/backoff.
- `trade_ledger.trade_id` gets a unique index when the existing DB has no
  duplicate `trade_id`; old dirty DBs fall back to a normal index and warning.
- Trade ledger appends use `INSERT OR IGNORE` to avoid double counting after a
  retry.
- Decision ledger appends are idempotent by `event_id`.
- Read-only ledger loading now sets SQLite timeout and `busy_timeout`.
- New CLI: `check-db-integrity`.
- New CLI: `score-filter-simulation`.
- New CLI: `paper-confidence`.
- Strategy gate documentation now includes `shadow_only`, `research_filter`,
  `candidate`, `paper_capital_allowed`, and `live_ready`.

## Safety Confirmation

- Live trading not enabled.
- Paper capital not enabled.
- No strategy promoted.
- Grid remains blocked by runtime policy.
- No Kraken order path touched.
- No UI visible change.
- New score simulation always reports `promotable=false`.
- New paper confidence report always reports `promotable=false`.

## Tests

Commands run locally:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_persistence_db_reliability.py tests\paper\test_p6_score_and_confidence.py -q
```

Result: 8 passed.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_loss_diagnostics.py tests\paper\test_official_performance.py tests\paper\test_shadow_observation_sync.py tests\test_v2_cli.py tests\test_persistence_db_reliability.py tests\paper\test_p6_score_and_confidence.py -q
```

Result: 63 passed.

```powershell
python -m compileall -q src
```

Result: passed.

## Local CLI Smoke

```powershell
python -m autobot.v2.cli check-db-integrity --state-db data/autobot_state.db --run-id p6_local_db_integrity --snapshot-dir reports/paper/db_integrity/snapshots --output-dir reports/paper/db_integrity
```

Result: `PASS_WITH_WARNINGS`. The local DB copy is legacy and lacks
`strategy_id` and `execution_mode`; the command reports this instead of failing
with a SQLite schema error.

```powershell
python -m autobot.v2.cli score-filter-simulation --state-db data/autobot_state.db --run-id p6_local_score_filter --output-dir reports/paper/score_filter_simulation
```

Result: 0 eligible trades on the local DB copy; all scenarios
`insufficient_data`, `promotable=false`.

```powershell
python -m autobot.v2.cli paper-confidence --state-db data/autobot_state.db --strategy-id trend_momentum --run-id p6_local_confidence_trend --bootstrap-iterations 200 --output-dir reports/paper/confidence
python -m autobot.v2.cli paper-confidence --state-db data/autobot_state.db --strategy-id mean_reversion --run-id p6_local_confidence_mean_reversion --bootstrap-iterations 200 --output-dir reports/paper/confidence
```

Result: 0 local evidence rows; both `insufficient_data`, `promotable=false`.

## Subagent Findings Integrated

- DB reliability: core ledger writes previously bypassed retry helpers; P6 now
  routes critical write paths through bounded retry/backoff and idempotent
  inserts.
- Statistical validation: positive score buckets or shadow samples cannot
  promote a strategy; confidence remains research-only with sample-size and
  bootstrap blockers.
- Regression/safety: no live/paper-capital activation, grid remains blocked,
  and simulation outputs cannot be used as promotion.

## Risks Remaining

- The local DB copy is legacy; VPS post-deploy must run `check-db-integrity`
  against the active schema.
- `StatePersistence.initialize()` still has a broader initialization critical
  section opportunity, but critical runtime write paths are now hardened.
- Some older reports and `.pyc` files are dirty/untracked locally and were not
  part of this P6 change.

## Next Step

Deploy P6, run the three new CLI checks on the VPS active DB, confirm container
health, live flags false, no orders, no paper capital, and no promotions.
