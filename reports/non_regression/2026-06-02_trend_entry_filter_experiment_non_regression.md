# Non-Regression - Trend Entry Filter Experiment - 2026-06-02

Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers a research-only experiment comparing stricter trend entry filters on the local VPS-derived dataset.

## Files Changed

- `reports/research/vps_trend_entry_filter_experiment_2026_06_02_summary.json`
- `reports/research/vps_trend_entry_filter_experiment_2026_06_02_summary.md`

No Python, dashboard, router, paper, live, risk, or execution code was changed in this slice.

## Runtime Safety

- Official paper execution: not modified.
- Live execution: not modified.
- Kraken integration: not modified.
- Strategy router: not modified.
- Risk manager: not modified.
- Registry promotion gates: not modified.
- Persistent runtime data: not modified.

## Evidence

The experiment replayed `trend` on 14 non-duplicated dashboard symbols from `data/vps_autobot_state_2026-06-01.db`.

Results:

- Baseline: `221` trades, `-115.803564` EUR net.
- `no_weak_breakout`: `94` trades, `-36.414494` EUR net.
- `strong_momentum`: `75` trades, `-27.351476` EUR net.
- `strong_breakout`: `24` trades, `-21.645635` EUR net.
- `high_atr_strong`: `6` trades, `-10.368624` EUR net.

Conclusion:

- Stricter entries reduce losses and costs, but none of the tested filters is profitable after modeled fees/spread/slippage.
- No tested configuration is eligible for official paper promotion.
- The best research candidate for the next replay slice is `strong_momentum`, but only as a baseline for further validation.

## Tests

No code changed in this slice. The immediately preceding setup-quality code slice was validated with:

- `pytest tests\research -q`: `49 passed in 0.43s`
- `pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q`: `24 passed in 0.17s`
- `python -m compileall -q src`: pass

## Risks Remaining

- This experiment is based on the currently available VPS price-sample dataset, not a long multi-regime historical dataset.
- Regime context is still missing from the replay journal, so regime-specific conclusions remain incomplete.
- Results support stricter filtering as a damage reducer, not as a proven edge.

## Next Recommended Action

Run a combined research-only matrix using `strong_momentum` entries with candidate exits, then add regime context to the validation journal before considering any official paper behavior change.
