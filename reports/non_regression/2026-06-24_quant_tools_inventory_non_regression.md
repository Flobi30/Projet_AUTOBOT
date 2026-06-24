# Non-Regression - Quant Tools Inventory and Research Diagnostics - 2026-06-24

## Verdict

`PASS_WITH_WARNINGS`

The added modules are pure research diagnostics and are attached to the research-only Strategy Orchestrator report. Focused tests pass. The warning is expected: current High Conviction evidence is below the existing 50 closed-trade review threshold, so robustness output must remain observational.

## Files Modified

- `src/autobot/v2/research/robustness_experiments.py` (new): deterministic bootstrap and conservative cost/fat-tail stress.
- `src/autobot/v2/research/purged_cv.py` (new): temporal purge/embargo planning only.
- `src/autobot/v2/research/fractal_features.py` (new): Hurst, fractal dimension and volatility clustering observations.
- `src/autobot/v2/research/strategy_orchestrator.py`: renders diagnostics without feeding strategy scoring, treasury allocation or promotion.
- `tests/research/test_advanced_quant_diagnostics.py` (new): deterministic bootstrap, one-way stress, purge/embargo and observation-only features.

## Commands and Results

```powershell
python -m py_compile src\autobot\v2\research\robustness_experiments.py src\autobot\v2\research\purged_cv.py src\autobot\v2\research\fractal_features.py src\autobot\v2\research\strategy_orchestrator.py
$env:PYTHONPATH='src'; python -m pytest tests\research\test_advanced_quant_diagnostics.py tests\research\test_strategy_orchestrator.py -q
```

Result: `18 passed`.

## What Did Not Change

- No runtime strategy, router, risk manager, sizing, paper executor, live executor or Kraken client was changed.
- No trading flag was changed.
- No paper or live order can be created by the new code.
- No strategy is promoted; `paper_candidate_allowed=false` and `live_promotion_allowed=false` remain explicit.
- No instance child is created and `ENABLE_INSTANCE_SPLIT_EXECUTOR` remains outside this work.

## Remaining Risks

- Bootstrap and stress diagnostics can describe fragility but cannot create statistical certainty from a small sample.
- Purged CV remains planning-only until a future model-selection workflow consumes it.
- Fractal features are descriptive; treating them as alpha before validation would be overfitting.

## Next Step

Safe to continue accumulating data and use the daily Strategy Orchestrator reports. Do not change paper/live behaviour from these observations.
