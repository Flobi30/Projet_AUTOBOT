# P18H Research Data Expansion Non-Regression - 2026-07-10

## Verdict

PASS_WITH_WARNINGS

P18H adds a research-only data capability scanner and scheduler reporting integration. No live, paper capital, promotion, sizing, leverage, UI, runtime order path, or strategy execution path was modified.

Warning: the local scan found duplicated OHLCV rows across research folders (`duplicate_count=126304`). This does not activate any strategy; it means future backfills must write canonical deduped datasets before retesting rejected OHLCV hypotheses.

## Files Modified

- `src/autobot/v2/research/data_capability_scanner.py`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_data_capability_scanner.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`
- `reports/research/p18h_research_data_expansion_plan_2026-07-10.md`
- `reports/research/p18h_research_data_expansion_plan_2026-07-10.json`

## Commands Run

- `python -m compileall -q src` - PASS
- `$env:PYTHONPATH='src'; python -m pytest tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py -q` - 19 passed
- `$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py -q` - 17 passed
- `$env:PYTHONPATH='src'; python -m pytest tests\paper tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q` - 135 passed
- `$env:PYTHONPATH='src'; python -m autobot.v2.cli data-capability-scan --run-id p18h_research_data_expansion_plan_2026-07-10 --state-db data/autobot_state.db --data-roots data/research,reports/research --memory-path reports/research/alpha_research_memory.json --output-dir reports/research` - PASS

## Data Findings

- Spot OHLCV: available, 236407 deduped-by-scanner rows, 20 symbols/aliases, 1m/5m/15m/1h, quality `dedupe_required`.
- Multi-symbol OHLCV: available.
- Spread/depth snapshots: available, 434 rows, top-of-book/depth only.
- Funding rates: missing.
- Perp/futures prices and spot/perp basis: missing.
- Open interest: missing.
- Liquidation events: missing.
- News/sentiment: missing.
- Slippage/fill history: insufficient in local `data/autobot_state.db`.

## Scheduler Behavior

- Rejected OHLCV hypotheses remain blocked unless a significant new data signature, new historical period, new thesis, or new template is recorded.
- `funding_basis` remains `DATA_MISSING`.
- `liquidation_cascade` remains `DATA_MISSING`.
- `order_flow_imbalance` is data-visible but remains research-only because current depth is sampled top-of-book, not full replay-grade order book data.

## Live Safety

- No order path was imported or called by the scanner.
- No live flag was changed.
- No paper capital flag was changed.
- No strategy was promoted.
- No shadow activation was added.
- Grid remains no-go.

## Recommendation

P18I should focus on bounded data acquisition, not new strategies:

- build canonical deduped OHLCV storage before retesting OHLCV families;
- evaluate real funding/basis/open-interest sources for `funding_basis`;
- evaluate real liquidation-event data sources for `liquidation_cascade`;
- expand spread/depth collection only as research data, not runtime execution.
