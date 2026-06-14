# Cost Profile Parity Design - 2026-06-14

## Scope

Local-only patch. No VPS access, deployment, restart, flag change, Kraken order,
strategy promotion, sizing/risk change, position close, or instance split.

## Canonical Profiles

| Profile | Maker fee | Taker fee | Default legs | Spread | Slippage / latency | Estimated round trip | Comparable to current paper |
| --- | ---: | ---: | --- | --- | --- | ---: | --- |
| `paper_current_taker` | 25 bps | 40 bps | taker/taker | observed top-of-book, 8 bps fallback | 3 bps/leg, 0 latency | 94 bps | yes |
| `paper_current_maker` | 25 bps | 40 bps | maker/maker | post-only, no crossing | 0 bps | 50 bps | yes, only with realistic post-only fills |
| `research_stress` | 25 bps | 40 bps | taker/taker | observed top-of-book, 8 bps fallback | 4 bps/leg + 1 bps latency/leg | 98 bps | yes, conservative |
| `research_legacy` | 10 bps | 16 bps | taker/taker | fixed/observed, 8 bps fallback | 4 bps/leg + 1 bps latency/leg | 50 bps | no |

`research_legacy` remains available for historical comparisons, but every
serialized configuration marks it `legacy=true` and
`runtime_comparable=false`.

## Integration

- `src/autobot/v2/cost_profiles.py` is the shared source of canonical profile assumptions.
- `ExecutionCostConfig` now serializes profile name, maker/taker fees, spread and slippage models, latency, legacy/comparability flags and round-trip estimate.
- Backtest reports print string and numeric cost metadata explicitly.
- Research trade journals retain the complete cost configuration for each closed trade.
- Main research CLI commands accept `--cost-profile`; numeric flags remain optional explicit overrides.
- Direct validation/matrix/regime CLIs accept the same profile names.
- Grid and strategy experiment defaults now use `research_stress` instead of the historical 16 bps default.
- `PaperTradingExecutor` still charges 25 bps maker and 40 bps taker and now exposes its detected profile in its summary.
- The runtime cost guard obtains its unchanged 40 bps entry fee and 6 bps round-trip slippage fallback from `paper_current_taker`, and records the profile/model names in edge context.

The research edge gate was aligned with the fill simulator: each simulated
leg charges half of the quoted spread. Previously the gate counted the full
spread on each leg while the fill simulator counted half per leg.

## Important Maker Constraint

Selecting `paper_current_maker` does not relabel market orders as maker fills.
The strategy/replay must emit realistic limit/post-only orders and satisfy the
existing limit fill rules. This prevents an optimistic maker-fee shortcut.

## Example Commands

BCHEUR grid replay with current paper taker assumptions:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli backtest --run-id bcheur_paper_taker --strategy grid --data-source csv --data-path <BCHEUR_OHLCV.csv> --symbol BCHEUR --cost-profile paper_current_taker
```

Conservative multi-pair research:

```powershell
python -m autobot.v2.cli strategy-experiments-batch --run-id parity_stress --data-source csv --data-path <OHLCV.csv> --symbols BCHEUR,LINKEUR,XLMZEUR --cost-profile research_stress
```

Historical comparison only:

```powershell
python -m autobot.v2.cli matrix --run-id legacy_comparison --data-source csv --data-path <OHLCV.csv> --symbols BCHEUR --strategies grid --cost-profile research_legacy
```

Maker scenario, only when the strategy generates realistic post-only orders:

```powershell
python -m autobot.v2.cli backtest --run-id bcheur_maker_scenario --strategy grid --data-source csv --data-path <BCHEUR_OHLCV.csv> --symbol BCHEUR --cost-profile paper_current_maker
```

## Files Modified

- `src/autobot/v2/cost_profiles.py`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/paper_trading.py`
- `src/autobot/v2/signal_handler_async.py`
- `src/autobot/v2/research/execution_cost_model.py`
- research validation, matrix, experiment, batch and regime runners
- report type annotations and backtest Markdown rendering
- targeted tests under `tests/research/` and `tests/test_v2_cli.py`

## Validation

```text
python -m compileall -q src
PYTHONPATH=src python -m pytest tests/research tests/test_v2_cli.py tests/test_paper_trading.py tests/paper/test_paper_trading_engine.py tests/test_signal_handler_async_unit.py tests/test_strategy_router.py -q
210 passed in 2.50s
```

No result was made positive by lowering fees. The new default research profile
is materially more conservative than the legacy profile.

## Conclusion

The canonical profiles are created and selectable. Research/backtest/replay
outputs now identify their assumptions and can be compared with current paper
fees. Nothing was deployed.
