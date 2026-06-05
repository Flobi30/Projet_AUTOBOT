# Non-Regression - 2026-06-05 Grid Experiments

Verdict: PASS_WITH_WARNINGS

## Scope

Implemented a research-only grid experiment campaign to test whether grid variants can reduce
`weak_mfe_below_cost` and improve MFE/Cost, exit capture, net PnL, and profit factor.

No live trading code was changed. No runtime paper sizing, runtime risk manager, strategy router,
Kraken credentials, dashboard, or Docker/VPS process was modified.

## Files Modified

- `src/autobot/v2/research/strategy_signal_generators.py`
  - Added research-only `GridResearchConfig` filters and exit modes.
  - Added cost-aware MFE/Cost gate, volatility gates, regime gates, spread gate, support confirmation,
    cost-buffered TP, MFE trailing, time stop, and decaying-net-edge exit.
  - Defaults keep the baseline grid behavior comparable unless options are explicitly enabled.
- `src/autobot/v2/research/grid_experiment_runner.py`
  - New research-only runner for conservative grid variants.
  - Builds a dataset from `market_price_samples`, runs backtests, loss attribution, scorecards,
    baselines, and walk-forward only for prequalified candidates.
  - Always reports `live_promotion_allowed=false`.
- `src/autobot/v2/cli.py`
  - Added `grid-experiments` command.
- `tests/research/test_strategy_signal_generators.py`
  - Added tests for research-only filters and grid exit modes.
- `tests/research/test_grid_experiment_runner.py`
  - Added runner and CLI smoke tests.

## Safety Confirmation

- Live trading unchanged.
- Runtime paper/live engines unchanged.
- Runtime `grid_async.py` unchanged.
- Runtime risk manager unchanged.
- Strategy router/promotion gate unchanged.
- Dashboard unchanged.
- No registry mutation.
- No Kraken key access.
- No Docker restart.
- `/health` checked without restart: `healthy`, orchestrator `running`, websocket `connected`, instances `14`.

## Commands Run

```powershell
$env:PYTHONPATH='src'; python -m compileall -q src
```

Result: PASS.

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests\research\test_strategy_signal_generators.py tests\research\test_grid_experiment_runner.py -q
```

Result: `16 passed in 0.36s`.

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests\test_v2_cli.py tests\research -q
```

Result: `116 passed in 1.24s`.

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

## Grid Experiment Run

Command:

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m autobot.v2.cli grid-experiments --run-id vps_2026_06_05_grid_experiments --state-db data\vps_autobot_state_2026-06-04_2026-06-04_121159.db --symbols BTCZEUR,ETHZEUR,SOLEUR,LTCZEUR,XLMZEUR,XRPZEUR,TRXEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --timeframe 5m --output-dir reports\research\grid_experiments\vps_2026_06_05_grid_experiments --dataset-output-dir data\research\grid_experiments\vps_2026_06_05_grid_experiments --min-closed-trades 1 --candidate-min-closed-trades 100 --train-window-bars 200 --test-window-bars 100 --step-window-bars 100 --min-folds 3
```

Result: PASS, 364 experiment cells, 26 variants, 14 symbols.

Cost assumptions:

- Fee: `16` bps
- Spread: `8` bps
- Slippage: `4` bps
- Latency buffer: `1` bps
- Estimated round-trip cost: `50` bps

Baseline current:

| Trades | Gross PnL | Net PnL | PF Proxy | MFE/Cost | Exit Capture | Max DD | Passes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 484 | -178.67 | -333.55 | 0.00 | 0.962 | -36.88 bps | 6.00% | 0 |

Top variants by loss reduction:

| Variant | Family | Trades | Net PnL | MFE/Cost | Exit Capture | Passes | Risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `range_only_filter` | regime_range_only_filter | 31 | -25.75 | 0.662 | -51.00 bps | 0 | single_symbol_dominated |
| `min_volatility_atr50_tp100` | min_volatility_filter | 82 | -35.95 | 2.085 | -11.83 bps | 0 | single_symbol_dominated |
| `wider_grid_spacing_r10_l5_tp140` | wider_grid_spacing | 51 | -57.11 | 2.057 | -79.91 bps | 0 | single_symbol_dominated |
| `wider_grid_spacing_r7_l7_tp100` | wider_grid_spacing | 211 | -149.99 | 1.594 | -39.05 bps | 0 | no_positive_evidence |
| `min_volatility_atr25_tp70` | min_volatility_filter | 289 | -195.31 | 1.378 | -35.55 bps | 0 | no_positive_evidence |

No variant passed the candidate-shadow criteria.

Best-by-symbol notes:

- `ADAEUR`, `BCHEUR`, `ETHZEUR`, `LINKEUR` had tiny positive best cells, but failed due to insufficient trades
  and/or incomplete statistical evidence.
- Most other symbols either had no profitable cell or selected a no-trade-like filtered result, which is not
  a viable grid candidate.
- `AAVEEUR`, `ATOMEUR`, `AVAXEUR`, `BTCZEUR`, `DOTEUR`, `ETHZEUR`, `LTCZEUR`, `SOLEUR`, `TRXEUR`,
  `XLMZEUR`, `XRPZEUR` were marked grid-disabled candidates by the runner.

Conclusion from the runner:

> Grid is not currently viable on this dataset after costs.

Recommendation: keep grid in shadow/research only or disable it from official paper until a variant passes
net-PnL, MFE/Cost, exit-capture, sample-size, baseline, and walk-forward criteria.

## Warnings / Residual Risk

- The dataset comes from `market_price_samples` aggregated to 5m OHLCV; it does not include real volume or
  order-book depth.
- Some variants reduce losses mostly by trading very little. That is useful evidence, but not a profitable
  strategy.
- No walk-forward candidate was produced because no backtest cell passed the prequalification criteria.
- Large generated experiment artifacts were not added to git; the CLI command above regenerates them.

## Next Step

Do not make grid more aggressive. The next sensible research step is to compare trend and mean-reversion
families with the same strict cost/baseline/walk-forward framework, then keep grid disabled or shadow-only
unless a future dataset shows robust, net-positive behavior.
