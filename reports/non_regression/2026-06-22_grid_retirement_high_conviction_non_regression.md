# Grid Retirement and High Conviction Non-Regression - 2026-06-22

## Verdict

`PASS`

Grid remains available only for explicitly requested, reproducible research. It
cannot be routed, promoted to official paper, or requested for live review.
The High Conviction portfolio replay remains isolated from runtime paper/live
trading and has been reviewed against a finite 500 EUR portfolio.

## Changed

- `src/autobot/v2/research/standard_audit_runner.py`
  - Standard audit defaults now run `trend,mean_reversion`; Grid is no longer a
    default research workload.
- `src/autobot/v2/research/research_paper_parity.py`
  - Direct library default matches the standard research universe.
- `src/autobot/v2/cli.py`
  - Default-strategy help now documents Grid as explicit archived research.
- `src/autobot/v2/strategy_validation_registry.py`
  - `dynamic_grid` is not promotable and cannot become paper/live eligible even
    if an invalid registry record were manually marked `paper_validated`.
- `src/autobot/v2/strategy_promotion_gate.py`
  - Retired Grid receives the explicit reason `grid_retired_research_only`.
- `tests/research/test_archived_grid_defaults.py`
  - New coverage for default research exclusion and all promotion paths.
- `tests/test_strategy_router.py`
  - The generic learning-status gate test now uses an active research engine;
    Grid has a dedicated retired-engine test.

## Runtime and Safety Boundaries

- Runtime still uses `ObservationOnlyStrategyAsync` for the active instances.
- `dynamic_grid` is rejected before router ranking through
  `is_runtime_engine_retired`.
- No dashboard, sizing, risk manager, paper fill model, order executor, Kraken
  client, Docker configuration, credentials, or feature flags were changed.
- No live permission, strategy promotion, order submission, leverage, or
  instance split was enabled.

## High Conviction 500 EUR Replay Review

Source: `reports/research/high_conviction_portfolio_2026_06_22/`.

Best comparable finite-capital scenario:

| Item | Result |
| --- | ---: |
| Cost profile | `paper_current_taker` |
| Policy | `dynamic_scaling` |
| Initial / final equity | `500.00 / 518.14 EUR` |
| Net PnL | `+18.14 EUR` |
| Trades | `9` |
| Profit factor | `4.49` |
| Win rate | `66.67%` |
| Max drawdown | `2.62%` |
| Average / planned max exposure | `40.20% / 60.00%` |
| Critical drawdown stop | `not triggered` |

The conservative variant produced `+17.98 EUR`; dynamic scaling added only
`+0.15 EUR`. The result is therefore not being driven by aggressive scaling.
It remains `research_only` because the sample has only nine closed trades,
below the configured minimum of thirty, and has not passed extended
out-of-sample validation.

Top contributors were LINKEUR (`+10.25 EUR`), DOTEUR (`+4.93 EUR`) and ADAEUR
(`+4.04 EUR`). SOLEUR and AVAXEUR were negative. No paper candidate is
recommended.

## Validation Evidence

```text
python -m compileall -q src
PASS

$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_strategy_router.py tests/test_strategy_validation_registry.py tests/test_opportunities_endpoint.py tests/test_v2_cli.py -q
230 passed in 3.66s

docker compose config -q
PASS

$env:PYTHONPATH='src'; python -m autobot.v2.cli high-conviction-portfolio-replay --help
PASS
```

## Remaining Limits

- High Conviction needs a longer, independently collected OHLCV history and
  walk-forward evidence before it can be considered for controlled paper
  review.
- Grid can still be invoked only through an explicit archived research command;
  it is intentionally not deleted so historical experiments remain
  reproducible.

## Next Step

Continue research data accumulation and run a longer High Conviction
portfolio-aware walk-forward replay. Do not enable paper execution or live
promotion from this result.
