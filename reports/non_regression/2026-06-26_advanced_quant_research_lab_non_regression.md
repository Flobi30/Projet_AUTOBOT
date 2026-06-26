# Advanced Quant Research Lab Non-Regression - 2026-06-26

## Verdict

PASS_WITH_WARNINGS.

The patch is research-only and does not modify runtime trading, paper official execution, live flags, sizing, risk, strategy promotion, or duplication execution.

## Files Modified

- `src/autobot/v2/research/advanced_market_analysis.py`
- `src/autobot/v2/research/statistical_validation.py`
- `src/autobot/v2/research/strategy_orchestrator.py`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/research/__init__.py`
- `tests/research/test_advanced_market_analysis.py`
- `tests/research/test_statistical_validation.py`
- `tests/research/test_strategy_orchestrator.py`
- `reports/research/advanced_quant_research_lab_2026-06-26.md`
- `reports/non_regression/2026-06-26_advanced_quant_research_lab_non_regression.md`

## What Changed

- Added Advanced Market Analysis snapshots from local OHLCV and optional microstructure profiles.
- Added a conservative Deflated Sharpe proxy and progressive PF quality gates.
- Extended Strategy Orchestrator signal meta-scores with market, robustness, MC, Purged CV, DSR, cost, liquidity, overfitting and PF-quality fields.
- Connected daily microstructure profiles to the research orchestrator.
- Kept all decisions as research-only recommendations.

## What Did Not Change

- No live trading flag changed.
- No paper official execution changed.
- No runtime router changed.
- No runtime risk manager changed.
- No sizing/risk runtime changed.
- No Kraken private key or private endpoint touched.
- No order creation path added.
- No strategy promoted.
- No real child instance created.
- No split executor activated.

## Tests

Commands executed:

- `python -m py_compile` on touched modules and tests: PASS.
- `pytest tests/research/test_advanced_market_analysis.py tests/research/test_statistical_validation.py tests/research/test_strategy_orchestrator.py -q`: PASS, 21 passed.
- `python -m compileall -q src`: PASS.
- `pytest tests/research tests/test_v2_cli.py -q`: PASS, 225 passed.

The first pytest attempt failed because `PYTHONPATH` was incorrectly expanded by nested PowerShell, causing `ModuleNotFoundError: autobot`. It was rerun with escaped `PYTHONPATH` and passed.

## Trading Safety

- `candidate_paper_recommended` remains false for the new PF gates.
- `live_promotion_allowed` remains false in all new result objects.
- `paper_candidate_allowed` remains false in all new diagnostics.
- `execution_authority` for market analysis is `none`.
- Strategy Orchestrator still does not import runtime orchestrator, order router, paper executor, Kraken client or state database.
- Instance split policy is still constructed with `executor_enabled=False`.

## Remaining Risks

- DSR is a proxy until AUTOBOT tracks a complete registry of trials/variants.
- Purged CV is still planning evidence; chronological walk-forward remains the primary validation.
- Trend and Mean Reversion still need portfolio-aware validation before they can compete with High Conviction for capital.
- Daily data accumulation remains necessary before any candidate review is meaningful.

## Recommendation

Proceed to broader research test suite and then deploy the research-only patch if tests remain green. Do not activate paper official, live, duplication or sizing changes.
