# P5 Opportunity Score Diagnostic - 2026-07-02

## Scope

Read-only strategy diagnosis plus targeted reliability hardening for the P4 shadow observation pipeline. No live trading, no paper-capital activation, no promotion, no sizing/leverage change, no UI change, and grid remains blocked.

Runtime baseline before the P5 patch:

- GitHub/VPS/container commit observed: `d9ebe4f7053d9ddf1fdab10e0a1407396ee233b8`
- Container: `autobot-v2` healthy
- WebSocket: connected
- Instances: 14
- PAPER_TRADING: still paper-only
- LIVE_TRADING_CONFIRMATION / live activation: not enabled

## Data Used

Post-P4 shadow observations in `trade_ledger`, closing legs only, `execution_mode=shadow_paper`, excluding legacy unattributed rows.

Latest P4 sync/diagnostic outputs reviewed:

- `reports/paper/post_p4_check/p4_check_latest_20260702_205432.md`
- `reports/paper/post_p4_check/p4_check_latest_20260702_205432_loss_diag.md`

Total shadow trades reviewed: 4010.

Scored coverage: 65 / 4010 trades.

## Bucket Performance

| Bucket | Trades | Gross PnL | Net PnL | Fees | Slippage | Gross PF | Net PF | Net Expectancy | Win Rate | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| high | 8 | 4.28 | 0.91 | 1.38 | 0.31 | 2.13 | 1.16 | 0.114 | 62.5% | 5.16 |
| medium | 40 | 7.04 | -3.31 | 4.23 | 0.95 | 1.81 | 0.78 | -0.083 | 57.5% | 10.49 |
| low | 17 | -4.55 | -6.38 | 0.74 | 0.17 | 0.02 | 0.00 | -0.375 | 0.0% | 6.38 |
| missing | 3945 | -225.42 | -623.35 | 162.29 | 36.51 | 0.72 | 0.42 | -0.158 | 31.6% | 623.83 |

Interpretation: the hierarchy is directionally coherent (`high > medium > low/missing`), but the scored sample is too small to be used for promotion or paper capital.

Confidence level: `early_signal`.

## Strategy Performance

| Strategy | Trades | Gross PnL | Net PnL | Fees | Slippage | Gross PF | Net PF | Net Expectancy | Win Rate | Max DD | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend_momentum | 2555 | -202.78 | -498.99 | 120.78 | 27.18 | 0.66 | 0.40 | -0.195 | 19.5% | 500.34 | shadow_only |
| mean_reversion | 1425 | -21.04 | -109.61 | 36.14 | 8.13 | 0.89 | 0.53 | -0.077 | 53.8% | 116.86 | shadow_only |
| high_conviction_swing | 30 | 5.18 | -23.52 | 11.72 | 2.64 | 1.17 | 0.54 | -0.784 | 26.7% | 30.73 | shadow_only |

High Conviction is now producing shadow observations, but the current sample is too small and net-negative after costs.

## Strategy By Bucket

| Strategy / Bucket | Trades | Net PnL | Net PF | Net Expectancy | Win Rate | Comment |
|---|---:|---:|---:|---:|---:|---|
| trend_momentum / high | 5 | 2.04 | 4.16 | 0.408 | 80.0% | Interesting but tiny sample |
| trend_momentum / medium | 33 | 4.20 | 1.96 | 0.127 | 63.6% | Early positive |
| trend_momentum / low | 17 | -6.38 | 0.00 | -0.375 | 0.0% | Clearly bad |
| trend_momentum / missing | 2500 | -498.85 | 0.39 | -0.200 | 19.0% | Main loss source |
| mean_reversion / missing | 1425 | -109.61 | 0.53 | -0.077 | 53.8% | No score coverage yet |
| high_conviction_swing / high | 3 | -1.13 | 0.78 | -0.377 | 33.3% | Not validated |
| high_conviction_swing / medium | 7 | -7.51 | 0.28 | -1.073 | 28.6% | Bad early result |
| high_conviction_swing / missing | 20 | -14.88 | 0.58 | -0.744 | 25.0% | Insufficient/negative |

The strongest early score effect is currently on `trend_momentum`, not on `high_conviction_swing`.

## Pair Highlights By Bucket

`high`:

- Best: `LINKEUR`, 4 trades, net PnL +2.68, 100% win rate.
- Worst: `BCHEUR`, 4 trades, net PnL -1.78, net PF 0.69.

`medium`:

- Best: `SOLEUR` +4.36, `ADAEUR` +2.26, `XETHZEUR` +1.44.
- Worst: `AAVEEUR` -4.08, `AVAXEUR` -2.85, `ATOMEUR` -1.75.

`low`:

- All 17 trades are net losers; bucket should remain blocked from any capital decision.

`missing`:

- Contains 3945 trades and most of the loss. Missing score must remain separate from low score, not merged into a neutral bucket.

## High Conviction Diagnosis

`high_conviction_swing` now writes closed `shadow_paper` observations, but:

- Total observed rows: 30
- Net PF: 0.54
- Net PnL: -23.52
- Net expectancy: -0.784
- Win rate: 26.7%

Important data-quality note: replay runs can produce duplicate economic trades if the replay `run_id` changes. P5 adds a stable High Conviction source id and an economic duplicate check so future syncs do not double-count the same replayed trade.

Conclusion: High Conviction remains `shadow_only`, insufficient and net-negative.

## Opportunity Score Recommendation

`opportunity_score` should become a `shadow_only` research filter candidate, not a promotion signal.

Current recommendation:

- Keep collecting.
- Treat `high` as `early_signal`.
- Treat `medium` as watch-only; costs currently flip gross positive to net negative.
- Treat `low` as blocked from future paper-capital consideration unless future evidence changes.
- Treat `missing` as separate and penalized/insufficient, because it contains most losses.
- Do not promote any strategy based on the current 8 high-bucket trades.

## Database Reliability Diagnostic

Observed issue:

- Recent `sqlite3.OperationalError: database is locked` on runtime persistence paths, including market samples and decision ledger writes.
- No duplicate trade ids were detected in the reviewed DB, but the prior High Conviction source id included replay `run_id`, allowing duplicate economic observations across repeated replays.

P5 hardening added:

- SQLite `timeout=30.0` and `PRAGMA busy_timeout=30000` for shadow sync.
- Commit after each shadow source, so a write transaction is not held while High Conviction replay is built.
- Stable High Conviction source id no longer includes replay `run_id`.
- Economic duplicate detection for High Conviction closing legs.
- Unique index on `trade_ledger.trade_id` for sync-created ledgers.
- Explicit negative cost rejection for High Conviction shadow records.

Remaining DB recommendation:

- Next P6 should review runtime persistence writes and reuse retry/backoff helpers for `append_decision_ledger_event`, `append_market_price_samples`, and purge paths.
- Diagnostics should prefer DB snapshots when doing heavy read-only analysis.

## Tests

Commands:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_loss_diagnostics.py tests\research\test_daily_data_collection_runner.py tests\test_v2_cli.py -q
python -m compileall -q src
```

Results:

- Targeted pytest: 59 passed.
- Compileall: passed.

## P5 Verdict

`opportunity_score`: `early_signal`, not usable for promotion.

`high_conviction_swing`: produces observations, but `insufficient_data` and net-negative.

DB reliability: improved for shadow sync; runtime persistence retry hardening remains a P6 task.

Promotion/paper-capital/live: not allowed.

## Recommended P6

1. Continue collecting scored observations until coverage is materially higher.
2. Add runtime DB write retry/backoff where lock errors are still possible.
3. Run score-vs-performance on a snapshot after the next daily cycle.
4. Test a research-only score filter simulation that excludes `low` and `missing`, without routing paper capital.
5. Keep all strategies `shadow_only` until sample size and PF gates are genuinely met.
