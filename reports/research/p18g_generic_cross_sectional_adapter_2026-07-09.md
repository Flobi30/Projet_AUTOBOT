# P18G Generic Cross-Sectional OHLCV Adapter - 2026-07-09

## Scope

- Mode: `research_only`.
- No live, no paper capital, no promotion, no shadow activation, no UI change, no sizing/leverage change.
- No runtime order path is imported or called.
- Grid remains no-go; trend/mean remain benchmark-only.

## What Changed

- Added `generic_cross_sectional_ohlcv_adapter`.
- Updated `leader_laggard_momentum` and `relative_strength_rotation` to use the generic adapter.
- Added template-specific runner selection with `--template-id`.
- Added template-specific rejection memory for cross-sectional hypotheses so one rejected template does not reject the whole family.
- Added `adapter_id` and `mode_used` to alpha research memory records.
- Updated Docker packaging to copy all `docs/research/` into the image so research CLI commands can run inside the container without manual mounts.

## Adapter Modes

| Mode | Inputs | Pre-entry logic | Exit/evaluation |
|---|---|---|---|
| `leader_laggard_momentum` | multi-symbol OHLCV, rolling correlation, relative returns, costs | detects a leader over a rolling lookback and tests long-only laggard candidates only when correlation and relative underperformance are known before entry | bounded hold after next-bar entry |
| `relative_strength_rotation` | multi-symbol OHLCV, relative strength rank, volatility, costs | ranks symbols by pre-entry return window and selects top ranks only when strength clears estimated costs | bounded hold/rebalance window |

## Anti-Lookahead

- Signal windows end before the entry bar.
- Entry is the next bar after signal detection.
- Future bars are used only for post-signal evaluation.
- No realized PnL, exit price, MFE/MAE, future close, or best historical PnL is used to create a signal.
- Variants are bounded by template order, not selected by best full-sample PnL.

## Scheduler Result

Command:

```bash
python -m autobot.v2.cli alpha-hypothesis-scheduler --state-db data/autobot_state.db --data-paths data/research/daily/ohlcv --run-id p18g_scheduler_local --output-dir reports/research/alpha_hypothesis_runner --max-variants 3 --max-symbols 6 --max-runtime-seconds 120 --no-memory-backfill
```

Result:

- Selected hypothesis: `cross_momentum`.
- Selected template: `leader_laggard_momentum`.
- Adapter: `generic_cross_sectional_ohlcv_adapter`.
- Status: `RUNNABLE_SMOKE`.
- Data rows: `15141`.
- Symbols: `ADAEUR`, `AVAXEUR`, `DOTEUR`, `LINKEUR`, `SOLEUR`, `TRXEUR`, `XRPZEUR`.
- Timeframes: `5m`, `15m`, `1h`.
- Next command included `--template-id leader_laggard_momentum`.

## Smoke Result

Command:

```bash
python -m autobot.v2.cli alpha-hypothesis-runner --hypothesis-id cross_momentum --mode smoke --state-db data/autobot_state.db --data-paths data/research/daily/ohlcv --output-dir reports/research/alpha_hypothesis_runner --max-variants 3 --max-symbols 6 --max-runtime-seconds 120 --template-id leader_laggard_momentum --run-id p18g_cross_momentum_leader_laggard_smoke_local
```

Verdict: `REJECT_FAST`.

Primary variant:

- `lookback_bars24__min_correlation0.45__min_relative_strength_bps150`

Metrics:

- trade_count: `53`
- PF net: `0.138464`
- net PnL EUR: `-147.515495`
- expectancy net: `-2.783311`
- max drawdown EUR: `158.38698`
- winrate: `28.301887%`
- total costs: `5194.0 bps`
- no-trade baseline: `0.0 EUR`

By symbol:

| Symbol | Trades | Net PnL EUR |
|---|---:|---:|
| `ADAEUR` | 21 | -92.699406 |
| `SOLEUR` | 19 | -32.118547 |
| `XRPZEUR` | 13 | -22.697542 |

Rejection reasons:

- `edge_net_not_positive`
- `profit_factor_net_not_above_1`
- `expectancy_net_not_positive`

## VPS Deployment And Auto-Selected Next Smoke

Deployed commit:

- `2df2c851b4b231ca70f6e9dd7a8fe8a089826f1b`

VPS note:

- SSH to the previously used `91.99.232.7` timed out on port 22.
- The operational AUTOBOT host was recovered from prior reports as `204.168.251.201`.
- Hostname confirmed: `AUTOBOT`.

VPS scheduler result after deployment:

- selected status: `RUNNABLE_SMOKE`
- selected hypothesis: `cross_momentum`
- selected template: `relative_strength_rotation`
- reason: `leader_laggard_momentum` was already rejected template-specifically in memory.

VPS smoke result for `relative_strength_rotation`:

- final_status: `REJECT_FAST`
- final_decision: `STOPPED`
- adapter_id: `generic_cross_sectional_ohlcv_adapter`
- mode_used: `relative_strength_rotation`
- trade_count: `42`
- PF net: `0.482841`
- net PnL EUR: `-37.949597`
- expectancy net: `-0.903562`
- reasons: `edge_net_not_positive`, `profit_factor_net_not_above_1`, `expectancy_net_not_positive`

No walk-forward was launched after the failed smoke gate.

## Memory

- Recorded in `reports/research/alpha_research_memory.json`.
- `adapter_id`: `generic_cross_sectional_ohlcv_adapter`.
- `mode_used`: `leader_laggard_momentum`.
- Template-specific rejection key: `cross_momentum__leader_laggard_momentum`.
- The family `cross_momentum` itself is not globally rejected, so `relative_strength_rotation` can still be selected by the scheduler later.

## Tests

```bash
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_generic_cross_sectional_ohlcv_adapter.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_alpha_hypothesis_scheduler.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Results:

- compileall: OK
- targeted tests: `23 passed`
- research/CLI non-regression: `282 passed`

## Safety

- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- No order path touched.
- No paper/live activation.
- No shadow activation.
- No strategy promotion.
- VPS `/health`: `healthy`.
- WebSocket: `connected`.
- Instances: `14`.
- VPS flags: `PAPER_TRADING=true`, `LIVE_TRADING_CONFIRMATION=false`, `STRATEGY_ROUTER_LIVE_ENABLED=false`, `COLONY_AUTO_LIVE_PROMOTION=false`.
- Container health: `healthy`.
- Critical runtime log count checked over last 200 lines: `0`.

## Recommendation P18H

Let the scheduler continue automatically. Since `leader_laggard_momentum` failed fast after costs, the next safe action is to let AUTOBOT select the next runnable cross-sectional template, likely `relative_strength_rotation`, and run only its smoke gate. Do not launch walk-forward unless a smoke result is positive enough to expose `WALK_FORWARD_AVAILABLE`.
