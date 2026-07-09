# Non-Regression - P17 High Conviction Historical Validation

Date: 2026-07-09
Scope: research-only validation run and reporting

## Verdict

`PASS_WITH_WARNINGS`

Warnings:

- High Conviction historical result is not paper-capital eligible.
- The OHLCV store contains many duplicate bars because daily rolling snapshots overlap; the runner deduplicated them before analysis.
- `score_v2` is not emitted by the historical walk-forward runner; it remains a shadow-ledger metadata path.

## Files Added

- `reports/research/p17_high_conviction_historical_validation_2026-07-09.md`
- `reports/non_regression/2026-07-09_p17_high_conviction_historical_validation_non_regression.md`

No runtime code was changed.

## Commands Run

VPS health and commit checks:

```bash
git rev-parse HEAD
docker ps --format '{{.Names}}\t{{.Status}}'
curl http://127.0.0.1:8080/health
```

Historical walk-forward:

```bash
python -m autobot.v2.cli high-conviction-walk-forward \
  --run-id p17_high_conviction_history_20260709 \
  --data-paths /app/data/research/daily/ohlcv \
  --output-dir /app/reports/research/high_conviction_walk_forward \
  --min-expected-move-bps 500 \
  --risk-reward-ratio 2 \
  --max-hold-hours 72 \
  --exit-modes fixed_tp_sl,trailing \
  --primary-exit-mode fixed_tp_sl \
  --initial-capital-eur 500 \
  --max-position-fraction 0.20 \
  --risk-per-trade-pct 0.01 \
  --max-global-exposure-pct 0.60 \
  --max-open-positions 3 \
  --cooldown-hours 6 \
  --max-daily-loss-pct 0.03 \
  --critical-drawdown-pct 0.12 \
  --train-window-bars 288 \
  --test-window-bars 192 \
  --step-window-bars 192 \
  --min-folds 3 \
  --min-positive-fold-ratio 0.60 \
  --min-closed-trades-for-review 50 \
  --min-profit-factor 1.30 \
  --max-drawdown-pct 0.10 \
  --max-single-symbol-positive-pnl-share 0.40
```

Local tests:

```bash
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_expected_move_diagnostics.py tests\paper\test_opportunity_score_audit.py -q
```

## VPS State

Runtime commit at validation start:

- `ae0e2ebf99ee1b670ddfbc4e8312b1ebb1df6ad5`

Runtime health:

- container `autobot-v2`: healthy
- `/health`: healthy
- websocket: connected
- instances: 14

Safety flags:

- `PAPER_TRADING=true`
- `LIVE_TRADING_CONFIRMATION=false`
- `STRATEGY_ROUTER_LIVE_ENABLED=false`
- `COLONY_AUTO_LIVE_PROMOTION=false`

## Trading Safety Confirmation

Confirmed:

- no live was enabled
- no paper capital was enabled
- no strategy was promoted
- no sizing or leverage was changed
- no UI was changed
- no Kraken order was created
- grid remains archived/no-go

## P17 Result Summary

Primary result, `research_stress / fixed_tp_sl / conservative`:

- trades: `82`
- PF net: `0.8772`
- net PnL: `-16.53 EUR`
- expectancy: `-0.2016 EUR/trade`
- win rate: `34.15%`
- positive folds: `4/13`
- verdict: `REJECT`

## Recommendation

Do not move to P17 paper-capital candidate logic. The next useful action is research-only segment diagnosis for High Conviction, especially:

- preserve BCHEUR/ADAEUR as watch-only segments;
- investigate XLMZEUR/AVAXEUR/AAVEEUR as destructive segments;
- compare fixed TP/SL against trailing exit;
- keep Trend and Mean Reversion as benchmark-only.
