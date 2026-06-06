# Non Regression - Strategy Experiments Research Runner - 2026-06-06

## Verdict

PASS_WITH_WARNINGS

The change adds a research-only experiment runner for `trend` and `mean_reversion`. It does not modify runtime paper execution, live execution, sizing, risk manager, strategy router, dashboard, Docker, Kraken keys, or persistent production data.

Warning: the VPS HTTP health endpoint is healthy, but SSH log inspection failed from this local session with `Permission denied (publickey,password)`. No server restart or deployment was performed.

## Scope

Base commit before this work: `5f4b296`.

Files changed:

- `src/autobot/v2/research/strategy_experiment_runner.py`
  - New research-only campaign runner for existing `trend` and `mean_reversion` validation variants.
  - Runs isolated validation replay, cost-aware scoring, baseline comparison, loss attribution, scorecard checks, and optional walk-forward for prequalified cells.
  - Keeps `live_promotion_allowed=false` for every cell.
  - Does not mutate `docs/research/strategy_hypotheses.json`.
- `src/autobot/v2/cli.py`
  - Adds `python -m autobot.v2.cli strategy-experiments`.
  - CLI parameters cover symbols, strategies, state DB, timeframe, output paths, conservative costs, candidate thresholds, and walk-forward windows.
- `tests/research/test_strategy_experiment_runner.py`
  - Adds coverage for variant construction, report generation, CLI execution, invalid strategy rejection, invalid cost rejection, and live-safety invariants.

Generated research artifacts were used for analysis and are not intended to be committed:

- `reports/research/strategy_experiments/vps_2026_06_06_strategy_experiments/`
- `data/research/strategy_experiments/vps_2026_06_06_strategy_experiments/`
- `reports/research/strategy_experiments/smoke_strategy_experiments_dev/`
- `data/research/strategy_experiments/smoke_strategy_experiments_dev/`

## What Must Not Have Changed

Confirmed unchanged by scope and tests:

- Dashboard routes and frontend behavior.
- Paper trading runtime.
- Live trading runtime.
- Strategy router and promotion gate behavior.
- Runtime risk management and sizing.
- Existing API contracts.
- Docker/VPS deployment state.
- Existing config files and secrets.
- Persistent AUTOBOT runtime databases.

## Safety Confirmation

- No live trading path is called by `strategy-experiments`.
- No Kraken API key is read or exposed by the runner.
- No order can be sent by the runner; it only runs validation/replay.
- No strategy is promoted automatically.
- Candidate output is limited to `candidate_shadow_only`.
- `live_promotion_allowed` is always false in experiment cells.
- Unknown/unsupported strategies are rejected instead of falling back permissively.
- Invalid cost parameters are rejected.

## Test Evidence

Targeted research tests:

```text
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests\research\test_strategy_experiment_runner.py tests\research\test_grid_experiment_runner.py tests\research\test_strategy_signal_generators.py -q
20 passed in 0.70s
```

Research + CLI regression tests:

```text
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests\test_v2_cli.py tests\research -q
120 passed in 1.49s
```

Python syntax validation:

```text
$env:PYTHONPATH='src'; python -m compileall -q src
PASS
```

## Research Campaign Evidence

Command:

```text
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m autobot.v2.cli strategy-experiments --run-id vps_2026_06_06_strategy_experiments --state-db data\vps_autobot_state_2026-06-04_2026-06-04_121159.db --symbols BTCZEUR,ETHZEUR,SOLEUR,LTCZEUR,XLMZEUR,XRPZEUR,TRXEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --strategies trend,mean_reversion --timeframe 5m --output-dir reports\research\strategy_experiments\vps_2026_06_06_strategy_experiments --dataset-output-dir data\research\strategy_experiments\vps_2026_06_06_strategy_experiments --min-closed-trades 1 --candidate-min-closed-trades 100 --train-window-bars 200 --test-window-bars 100 --step-window-bars 100 --min-folds 3
```

Campaign result:

- Strategies tested: `trend`, `mean_reversion`.
- Variants tested: 24.
- Cells tested: 336.
- Shadow candidates accepted: 0.
- Positive net cells: 5, but only 1 to 3 trades each.
- Positive gross cells: 38.
- Cells beating baseline: 4.
- Cells with trade_count >= 100: 0.
- Cells with average MFE/Cost >= 1.5: 40.
- Cells with positive average exit capture: 38.

Top aggregate variants by net PnL remained negative after costs:

| Strategy | Variant | Trades | Net PnL EUR | PF proxy | Avg MFE/Cost | Avg Exit Capture bps | Risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| trend | confirm_50 | 74 | -27.28 | 0.013 | 2.982 | -4.85 | small_sample |
| trend | min_atr_30 | 83 | -36.97 | 0.023 | 3.010 | -12.53 | single_symbol_dominated |
| trend | confirm_30 | 149 | -76.42 | 0.000 | 2.001 | -19.27 | no_positive_evidence |
| trend | momentum_60 | 180 | -78.83 | 0.000 | 2.011 | -11.78 | no_positive_evidence |
| trend | min_atr_15 | 173 | -83.20 | 0.000 | 2.002 | -16.08 | no_positive_evidence |
| mean_reversion | strict_combo | 210 | -116.55 | 0.018 | 0.754 | -23.48 | single_symbol_dominated |

Best single cells were not statistically usable:

- `mean_reversion/XLMZEUR strict_combo`: net +2.10 EUR, 3 trades, failed PF/sample/baseline.
- `trend/ADAEUR min_atr_30`: net +0.69 EUR, 2 trades, failed PF/sample.
- `trend/BTCZEUR confirm_50`: net +0.19 EUR, 1 trade, failed PF/sample.
- `trend/LINKEUR confirm_50`: net +0.18 EUR, 2 trades, failed sample.

Conclusion from generated report:

```text
No trend or mean-reversion variant passed the full shadow-candidate criteria on this dataset after costs. Keep them in research/shadow until a variant passes net-PnL, PF, MFE/Cost, exit-capture, baseline, sample-size and walk-forward checks.
```

## VPS Runtime Check

HTTP health:

```text
curl.exe -sS --max-time 20 http://204.168.251.201:8080/health
{"status":"healthy","timestamp":"2026-06-06T14:17:20.447372+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":727263.588731}}
```

SSH log inspection attempted:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 root@204.168.251.201 "cd /opt/Projet_AUTOBOT && docker compose ps && docker logs --tail 80 autobot 2>&1 | tail -80"
root@204.168.251.201: Permission denied (publickey,password).
```

The same result occurred with local `id_ed25519` and `id_deploy`. No VPS command was executed over SSH.

## Risks Remaining

- Dataset is built from `market_price_samples`; no full order-book depth or real historical volume is included in this experiment.
- The runner uses validation/replay models, not live execution.
- The campaign did not find viable candidates; it only proves the current simple variants should not be promoted.
- SSH log verification remains unavailable until the correct key/agent is restored.
- Full project pytest was not run here; this change is covered by research + CLI smoke/regression suites.

## Recommendation

Proceed to the next research layer only with caution:

1. Keep grid, trend, and mean-reversion in research/shadow until a variant passes the same criteria on richer data.
2. Improve data quality next: real OHLCV history, volume, spread/order-book snapshots, and longer periods.
3. Add batch validation across multiple historical windows before considering any paper-official promotion.
4. Do not make runtime trading more aggressive based on these results.

