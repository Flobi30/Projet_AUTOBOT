# P17 - High Conviction Historical Validation

Date: 2026-07-09
Run id: `p17_high_conviction_history_20260709`
Scope: research-only historical validation of `high_conviction_swing`

## Verdict

`REJECT` for the current High Conviction configuration.

This does not mean the whole swing idea is permanently dead, but the current implementation must not move to paper capital. On the available OHLCV history, the strict walk-forward result is net negative after costs, with too few positive out-of-sample folds and excessive dependence on a small number of winning symbols.

Safety status:

- `paper_capital_allowed=false`
- `live_allowed=false`
- `promotable=false`
- no order was created
- no live flag was changed
- grid remains archived/no-go

## Historical Data Inventory

Source checked on VPS/container:

- `/app/data/research/daily/ohlcv/`

The daily OHLCV research store contains rolling Kraken snapshots from:

- earliest detected bar: `2026-05-16T16:00:00Z`
- latest detected bar: `2026-07-09T00:15:00Z`
- latest fresh daily directory: `daily_2026_07_09T00_18_07Z`

Main symbols detected:

- `AAVEEUR`
- `ADAEUR`
- `ATOMEUR`
- `AVAXEUR`
- `BCHEUR`
- `BTCZEUR`
- `DOTEUR`
- `ETHZEUR`
- `LINKEUR`
- `LTCZEUR`
- `SOLEUR`
- `TRXEUR`
- `XLMZEUR`
- `XRPZEUR`

Main timeframes detected:

- `5m`
- `15m`
- `1h`

The walk-forward loader read:

- raw bars: `792379`
- deduplicated bars: `159782`
- duplicate bars ignored: `632597`
- folds: `13`

The high duplicate count is expected from overlapping daily rolling snapshots. The validation used the deduplicated bar set.

## Replay Configuration

Command executed on VPS:

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

Notes:

- `--max-drawdown-pct 0.10` means 10%.
- Costs were not reduced.
- This run was research-only and did not write orders.

## Primary Result

Primary scenario:

- cost profile: `research_stress`
- exit mode: `fixed_tp_sl`
- portfolio policy: `conservative`
- initial capital: `500 EUR`

Metrics:

- trades: `82`
- net PnL: `-16.53 EUR`
- net profit factor: `0.8772`
- net expectancy: `-0.2016 EUR/trade`
- win rate: `34.15%`
- folds: `13`
- positive folds: `4`
- worst fold drawdown: `4.22%`
- average fold drawdown: `2.60%`
- single-symbol dominated: `true`
- largest positive symbol share: `47.41%`

Decision emitted by the runner:

- status: `research_only_keep_testing`
- reasons:
  - `insufficient_positive_out_of_sample_folds`
  - `non_positive_net_pnl_after_costs`
  - `profit_factor_below_threshold`
  - `single_symbol_concentration`
  - `no_automatic_paper_or_live_promotion`

Under the P17 hard criteria, this maps to `REJECT` for paper-capital readiness because PF net is below 1 and expectancy is negative out-of-sample.

## Walk-Forward Folds

Primary `research_stress / fixed_tp_sl / conservative` folds:

| Fold | Test period UTC | Trades | Net PnL EUR | PF | Expectancy EUR | Max DD % | Win rate % |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 2026-06-11 04:00 -> 2026-06-13 03:45 | 0 | 0.00 | n/a | n/a | 0.00 | n/a |
| 2 | 2026-06-13 04:00 -> 2026-06-15 03:45 | 5 | 24.30 | 12.51 | 4.86 | 1.91 | 80.00 |
| 3 | 2026-06-15 04:00 -> 2026-06-17 03:45 | 7 | 18.70 | 3.93 | 2.67 | 2.74 | 71.43 |
| 4 | 2026-06-17 04:00 -> 2026-06-19 03:45 | 6 | -18.95 | 0.00 | -3.16 | 4.01 | 0.00 |
| 5 | 2026-06-19 04:00 -> 2026-06-21 03:45 | 6 | -2.89 | 0.61 | -0.48 | 1.51 | 33.33 |
| 6 | 2026-06-21 04:00 -> 2026-06-23 03:45 | 3 | -6.03 | 0.00 | -2.01 | 1.89 | 0.00 |
| 7 | 2026-06-23 04:00 -> 2026-06-25 03:45 | 9 | -4.69 | 0.67 | -0.52 | 3.66 | 33.33 |
| 8 | 2026-06-25 04:00 -> 2026-06-27 03:45 | 9 | -3.30 | 0.81 | -0.37 | 3.36 | 33.33 |
| 9 | 2026-06-27 04:00 -> 2026-06-29 03:45 | 6 | -14.00 | 0.00 | -2.33 | 3.31 | 0.00 |
| 10 | 2026-06-29 04:00 -> 2026-07-01 03:45 | 10 | -11.97 | 0.38 | -1.20 | 4.22 | 20.00 |
| 11 | 2026-07-01 04:00 -> 2026-07-03 03:45 | 10 | 5.02 | 1.44 | 0.50 | 2.22 | 50.00 |
| 12 | 2026-07-03 04:00 -> 2026-07-05 03:45 | 5 | 12.22 | 5.46 | 2.44 | 2.05 | 80.00 |
| 13 | 2026-07-05 04:00 -> 2026-07-07 03:45 | 6 | -14.92 | 0.00 | -2.49 | 2.98 | 0.00 |

Interpretation:

- The signal is not stable across time.
- It had two strong early folds and two later positive folds, but most folds were negative.
- This looks like intermittent opportunity capture, not a robust deployable edge.

## Scenario Comparison

| Cost profile | Exit | Policy | Trades | Net PnL EUR | PF net | Expectancy EUR | Positive folds |
|---|---|---|---:|---:|---:|---:|---:|
| paper_current_taker | fixed_tp_sl | dynamic_scaling | 82 | -13.11 | 0.9012 | -0.1599 | 4/13 |
| paper_current_taker | fixed_tp_sl | conservative | 82 | -13.29 | 0.8997 | -0.1621 | 4/13 |
| research_stress | fixed_tp_sl | dynamic_scaling | 82 | -16.36 | 0.8787 | -0.1996 | 4/13 |
| research_stress | fixed_tp_sl | conservative | 82 | -16.53 | 0.8772 | -0.2016 | 4/13 |
| paper_current_taker | trailing | conservative | 98 | -43.86 | 0.6796 | -0.4475 | 3/13 |
| paper_current_taker | trailing | dynamic_scaling | 98 | -44.06 | 0.6788 | -0.4496 | 3/13 |
| research_stress | trailing | conservative | 98 | -47.73 | 0.6569 | -0.4870 | 3/13 |
| research_stress | trailing | dynamic_scaling | 98 | -47.94 | 0.6562 | -0.4891 | 3/13 |

The fixed TP/SL exit is less bad than trailing. Dynamic scaling does not rescue the edge and should remain research-only.

## Symbol Attribution

Primary scenario contributors:

| Symbol | Trades | Net PnL EUR |
|---|---:|---:|
| BCHEUR | 13 | 24.71 |
| ADAEUR | 5 | 16.30 |
| XRPZEUR | 4 | 4.70 |
| SOLEUR | 8 | 4.38 |
| LTCZEUR | 2 | 2.03 |
| ETHZEUR | 4 | -1.56 |
| LINKEUR | 1 | -1.92 |
| ATOMEUR | 1 | -2.24 |
| DOTEUR | 5 | -4.48 |
| AAVEEUR | 15 | -14.45 |
| AVAXEUR | 10 | -18.69 |
| XLMZEUR | 14 | -25.32 |

Interpretation:

- BCHEUR and ADAEUR carry most of the positive result.
- XLMZEUR, AVAXEUR, and AAVEEUR destroy the portfolio.
- The positive side is too concentrated to justify candidate status.

## Benchmark Comparison

Current shadow-paper benchmark ledger, attributed post-P0/P1/P2:

| Strategy | Trades | Net PnL EUR | PF net | Expectancy EUR | Win rate % |
|---|---:|---:|---:|---:|---:|
| trend_momentum | 5966 | -541.13 | 0.4108 | -0.0907 | 10.56 |
| mean_reversion | 3268 | -121.88 | 0.5292 | -0.0373 | 26.59 |
| high_conviction_swing | 176 | -3.14 | 0.9756 | -0.0179 | 17.61 |

High Conviction is materially better than Trend and Mean Reversion, but still not positive enough to justify paper capital.

No-trade baseline:

- net PnL: `0 EUR`
- drawdown: `0`
- High Conviction under this historical P17 run does not beat no-trade after costs.

## Score V2 / Expected Move

This historical walk-forward runner is OHLCV/research based and does not route through the live shadow ledger opportunity-score stamping path. Therefore:

- `expected_move_bps` is enforced by scenario threshold: `500 bps`
- costs are included through `paper_current_taker` and `research_stress`
- `score_v2` distribution is not emitted by this runner and was not used as a promotion signal

This is acceptable for P17 because the decision is based on net out-of-sample performance after costs, not score calibration.

## Decision Against P17 Criteria

Hard criteria:

- `REJECT` if PF net < 1.0 or expectancy negative on OOS
- `WEAK_SIGNAL` if PF net 1.0-1.2 or sample too weak
- `KEEP_RESEARCH` if PF net > 1.2 with sufficient sample
- `PAPER_CANDIDATE_LATER` only if PF net > 1.3, controlled drawdown, multiple positive folds, sufficient sample

Result:

- PF net: `0.8772` under `research_stress`
- expectancy: `-0.2016 EUR/trade`
- positive folds: `4/13`
- net PnL: `-16.53 EUR`
- single-symbol concentration: `true`

Verdict: `REJECT` for this configuration.

## Recommendation P18

Do not wait for this exact configuration to become paper-capital ready.

Recommended next step:

1. Keep `high_conviction_swing` research-only, but split it into diagnostic sub-families, not new strategies:
   - BCHEUR/ADAEUR positive segments for observation only;
   - XLMZEUR/AVAXEUR/AAVEEUR destructive segments for shadow reduction or block-shadow review.
2. Add a strict segment exclusion simulation:
   - read-only;
   - no optimization on realized PnL;
   - tests that exclusions are derived from prior folds only.
3. Investigate why trailing exit is worse than fixed TP/SL.
4. Keep Trend and Mean Reversion as benchmark-only unless redesigned.

No paper capital should be enabled from P17.
