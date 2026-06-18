# High Conviction Swing Research Non-Regression - 2026-06-18

## Verdict

PASS

## Scope

This patch adds a research-only high-conviction / swing replay tool. It is designed to test whether AUTOBOT should prefer fewer trades with larger expected move, multi-timeframe context, mandatory stop-loss, wider take-profit, trailing exit, partial take-profit and longer holding windows.

## Files Modified

- `src/autobot/v2/research/high_conviction_swing.py`
  - New read-only replay/report module.
  - Reads `decision_ledger` and `market_price_samples` through SQLite `mode=ro`.
  - Produces Markdown and JSON reports.
  - Computes expected-move buckets, asymmetric candidate scores, multi-timeframe context and swing scenario metrics.
- `src/autobot/v2/cli.py`
  - Adds `high-conviction-swing` research command.
  - Adds CSV float parsing helper for scenario grids.
- `tests/research/test_high_conviction_swing.py`
  - Adds unit and CLI coverage for expected-move buckets, micro-signal filtering, cost subtraction, MTF blocking and report writing.

## What Did Not Change

- No live trading flags changed.
- No paper runtime behavior changed.
- No strategy router or governance gate changed.
- No cost guard or microstructure filter changed.
- No sizing, leverage, risk manager, execution engine or duplication logic changed.
- No strategy is promoted.
- No Kraken order path is called.

## Tests

Commands executed locally:

```powershell
python -m py_compile src\autobot\v2\research\high_conviction_swing.py src\autobot\v2\cli.py
$env:PYTHONPATH='src'; python -m pytest tests\research\test_high_conviction_swing.py -q
$env:PYTHONPATH='src'; python -m pytest tests\test_v2_cli.py -q
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Results:

- `py_compile`: PASS
- `tests/research/test_high_conviction_swing.py`: 4 passed
- `tests/test_v2_cli.py`: 25 passed
- `compileall`: PASS
- `tests/research`: 155 passed

## Runtime Safety Check

VPS read-only pre-deploy check:

- VPS commit before patch: `bc4c8a0`
- Container: `autobot-v2 Up 22 hours (healthy)`
- `/health`: healthy, websocket connected, 14 instances

## Remaining Risk

- The first real report still depends on VPS `decision_ledger` and `market_price_samples` coverage after deployment.
- The tool can identify a `shadow_candidate` scenario, but this remains research-only evidence and cannot promote paper/live execution.

## Next Step

Deploy the patch, run:

```bash
python -m autobot.v2.cli high-conviction-swing \
  --run-id high_conviction_swing_2026_06_18 \
  --state-db /opt/Projet_AUTOBOT/autobot_state.db \
  --lookback-hours 72 \
  --cost-profile research_stress
```

Then inspect the generated Markdown/JSON report before considering any controlled paper-only strategy change.
