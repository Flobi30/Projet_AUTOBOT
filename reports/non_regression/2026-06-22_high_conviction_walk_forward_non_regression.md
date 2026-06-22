# High Conviction Walk-Forward Non-Regression - 2026-06-22

## Verdict

`PASS`

The new High Conviction walk-forward runner is research-only. It reads
collected OHLCV, uses portfolio constraints within every out-of-sample fold,
and cannot promote, execute, or modify runtime trading.

## Collection Verification

The VPS research collector is already active and isolated:

- `autobot-research-data.timer` runs daily at `02:15 Europe/Paris` with a
  bounded random delay;
- the latest successful run produced OHLCV files, 840 public spread/depth
  snapshots, a microstructure profile and a data-readiness report;
- the collector uses a read-only, unprivileged container with only research
  data/report mounts. It does not mount `.env`, the runtime DB or trading logs.

The patch extends this existing collection run with an automatic High
Conviction walk-forward report. It scans all accumulated daily OHLCV, not only
the newly fetched files, and deduplicates bars by symbol, timeframe and
timestamp before validation.

## New Validation Contract

- Initial capital: `500 EUR` per independent out-of-sample fold.
- Cost profiles: `paper_current_taker` and `research_stress`.
- Portfolio controls: finite cash, dynamic equity, max position fraction, max
  global exposure, max concurrent positions, one position per pair, cooldown,
  daily-loss stop, drawdown reduction and critical drawdown stop.
- Scenario: at least `500 bps` expected move, `1:2` risk/reward and `72h`
  holding horizon. Fixed TP/SL and trailing variants are reported, but the
  conservative stress / fixed TP/SL path is the validation reference.
- Minimum evidence: `50` closed trades, `3` folds, positive performance on
  the configured proportion of folds, PF at least `1.20`, drawdown at most
  `12%`, and no single-pair concentration.
- Passing every research threshold still produces only
  `research_only_human_review_required`. It never enables official paper or
  live trading.

## Files Changed

- `src/autobot/v2/research/high_conviction_walk_forward.py`
- `src/autobot/v2/research/high_conviction_portfolio.py`
- `src/autobot/v2/research/daily_data_collection_runner.py`
- `src/autobot/v2/cli.py`
- `config/research_data_collection.yaml`
- `deploy/systemd/run-autobot-research-collection.sh`
- `tests/research/test_high_conviction_walk_forward.py`
- `tests/research/test_high_conviction_portfolio.py`
- `tests/research/test_daily_data_collection_runner.py`

## Validation Evidence

```text
python -m compileall -q src
PASS

$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py tests/test_strategy_router.py tests/test_strategy_validation_registry.py tests/test_opportunities_endpoint.py -q
236 passed in 5.01s

docker compose config -q
PASS

bash -n deploy/systemd/run-autobot-research-collection.sh
PASS
```

## Safety Confirmation

- No live flag, paper flag, sizing, risk runtime, router, strategy runtime or
  instance-split setting changed.
- The daily runner remains public-market-data-only and cannot create an order.
- The walk-forward CLI has no Kraken client or runtime executor dependency.
- `paper_candidate_allowed=false` and `live_promotion_allowed=false` are
  asserted in tests and emitted in every generated report.

## Next Automatic Run

The next daily collection will run the new validation after fetching fresh
OHLCV, then write its result under:

`reports/research/high_conviction_walk_forward/`

It may correctly report insufficient folds or trades while data continues to
accumulate. That is an evidence status, not a failure and not a reason to
relax the thresholds.
