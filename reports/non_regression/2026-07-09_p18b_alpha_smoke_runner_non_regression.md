# P18B Alpha Smoke Runner Non-Regression - 2026-07-09

## Verdict

PASS_WITH_WARNINGS

P18B added and executed a bounded, read-only Alpha Hypothesis Lab smoke runner. It did not touch runtime trading, order paths, paper capital, sizing, leverage, promotion, or UI.

Warning: `volatility_breakout_high_conviction` is only a weak positive smoke result. It is not stable evidence and must go through walk-forward/OOS before any shadow or paper-capital consideration.

## Commits

- Code/report commit stamped in P18B report: `7748bf109cb34cc376398578a38b9bc6cd816fee`
- VPS repo HEAD after sync: `7748bf109cb34cc376398578a38b9bc6cd816fee`
- Main runtime container: not restarted for P18B

## Files Modified

- `src/autobot/v2/research/alpha_smoke_runner.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_alpha_smoke_runner.py`
- `reports/research/alpha_smoke/p18b_alpha_smoke_20260709.json`
- `reports/research/alpha_smoke/p18b_alpha_smoke_20260709.md`
- `reports/non_regression/2026-07-09_p18b_alpha_smoke_runner_non_regression.md`

## Commands Run

Local validation:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_smoke_runner.py tests\research\test_alpha_hypothesis_lab.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_archived_grid_defaults.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_alpha_smoke_runner.py tests\test_v2_cli.py -q
```

VPS read-only smoke runner:

```bash
cd /opt/Projet_AUTOBOT
docker run --rm --network none --user root \
  -v /opt/Projet_AUTOBOT:/app -w /app -e PYTHONPATH=/app/src \
  projet_autobot-autobot \
  python -m autobot.v2.cli alpha-smoke-runner \
  --run-id p18b_alpha_smoke_20260709 \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/alpha_smoke \
  --hypotheses-path /app/docs/research/alpha_hypotheses.json \
  --max-variants 3 \
  --max-symbols 6 \
  --max-cpu-seconds 60 \
  --cost-profile research_stress \
  --commit 7748bf109cb34cc376398578a38b9bc6cd816fee
```

## Test Results

- `compileall`: PASS
- Alpha smoke + hypothesis lab tests: 10 passed
- Paper tests: 72 passed
- Grid/governance/CLI non-regression: 46 passed
- Alpha smoke + CLI after commit-stamp patch: 31 passed

## VPS Runtime Safety

- `autobot-v2`: healthy
- `/health`: healthy
- WebSocket: connected
- Instances: 14
- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`
- `ENABLE_INSTANCE_SPLIT_EXECUTOR`: unset/not enabled

No main runtime restart was performed for P18B. The smoke runner was executed in a transient container with `--network none`.

## Data Used

- Source: `/opt/Projet_AUTOBOT/data/research/daily/ohlcv`
- Symbols used: `ADAEUR`, `BCHEUR`, `BTCZEUR`, `ETHZEUR`, `SOLEUR`, `XRPZEUR`
- Timeframes available: `5m`, `15m`, `1h`
- Period: `2026-05-16T16:00:00+00:00` to `2026-07-09T00:15:00+00:00`
- Deduped rows: 68,478
- Raw duplicates detected before dedupe: 275,439
- Gaps detected in smoke availability: 0

## Smoke Results

### volatility_breakout_high_conviction

- Verdict: `KEEP_RESEARCH`
- Best bounded variant: `fixed_tp_sl__min500bps__rr2__hold72h`
- Trade count: 206
- Net PF: 1.02477
- Net expectancy: 0.05336 EUR/trade
- Net PnL: 10.99 EUR
- Win rate: 36.89%
- Max drawdown proxy: 119.80 EUR
- Reason: weak positive smoke, requires walk-forward before any shadow consideration

Best/worst symbol contribution:

- `BCHEUR`: +93.77 EUR
- `ADAEUR`: +16.86 EUR
- `ETHZEUR`: -2.76 EUR
- `XRPZEUR`: -32.44 EUR
- `SOLEUR`: -64.44 EUR

### long_timeframe_adaptive_trend

- Verdict: `REJECT_FAST`
- Trade count: 404
- Net PF: 0.59920
- Net expectancy: -0.72322 EUR/trade
- Net PnL: -292.18 EUR
- Win rate: 34.41%
- Max drawdown proxy: 294.09 EUR
- Reason: net edge negative after costs across tested bounded variants

### Not Tested

- `funding_basis`: `MISSING_DATA`; Kraken Spot OHLCV store does not contain derivatives funding/basis data.
- `liquidation_cascade`: `MISSING_DATA`; Kraken Spot OHLCV store does not contain liquidation/event data.

## Trading Safety Confirmation

- No live trading enabled.
- No paper capital enabled.
- No promotion created.
- No order path touched.
- No sizing/leverage change.
- No UI change.
- Grid remains archived/no-go.
- Trend and mean reversion remain benchmark-only.

## Remaining Risks

- `volatility_breakout_high_conviction` result is weak and concentrated: BCHEUR/ADAEUR positive, SOLEUR/XRP negative.
- The smoke run is not walk-forward, not OOS, and not Monte Carlo.
- Funding/liquidation hypotheses cannot be tested until appropriate non-OHLCV data is collected.

## Recommendation P18C

Proceed only with research-only walk-forward/OOS for `volatility_breakout_high_conviction`, with segment attribution before any shadow consideration. `long_timeframe_adaptive_trend` should remain rejected/benchmark-only. Funding/liquidation should remain data-missing until the required data sources exist.
