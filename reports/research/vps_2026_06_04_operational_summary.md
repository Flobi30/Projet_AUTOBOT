# VPS Operational Validation - 2026-06-04

## Scope

Read-only validation from the AUTOBOT VPS state database. No runtime setting, strategy router, risk rule, paper execution path, registry status, or live trading behavior was changed.

## VPS Runtime Snapshot

- VPS commit: `96fce31` on `master`.
- Docker: `autobot-v2` up for about 6 days and `healthy`.
- `/health`: `healthy`, orchestrator `running`, websocket `connected`, `14` instances.
- Public capital endpoint without token returns `401 Token manquant`, which is expected for an unauthenticated call.
- Recent logs show the bot is active but mostly blocked in observe mode:
  - `strategy governance gate (abstain)`
  - `router_selected_no_trade`
  - `setup optimizer gate`
  - `execution_mode: observe_only`

## Fresh State DB Snapshot

- Snapshot source: `/opt/Projet_AUTOBOT/data/autobot_state.db`.
- Local snapshot: `data/vps_autobot_state_2026-06-04_2026-06-04_121159.db` (ignored by Git).
- DB size: about 63 MB.
- `market_price_samples`: `135046`, from `2026-05-28T09:56:44+00:00` to `2026-06-04T09:53:15+00:00`.
- `decision_ledger`: `3234`, from `2026-05-22T09:39:10+00:00` to `2026-06-04T06:42:22+00:00`.
- `signal_outcomes`: `2027`, from `2026-05-27T19:09:00+00:00` to `2026-06-04T07:43:11+00:00`.
- `trade_ledger`: `1142`, but last recorded official paper trade is `2026-05-21T10:41:49+00:00`.

## Important Correction Found

The first paper/research comparison reported `+68.866444 EUR` official paper net PnL. That was incorrect.

Root cause: old `trade_ledger` closing rows with missing `realized_pnl` were converted into TradeJournal records by inferring PnL from `entry_price`, `exit_price`, and `volume`. Some old rows had incoherent legacy prices, for example an `XETHZEUR` closing leg at `60000.0`, creating false paper profit.

Correction: `load_state_db_paper_ledger()` now skips state DB closing legs without `realized_pnl` and records a `realized_pnl_missing:<id>` warning instead of inventing PnL.

Corrected official paper evidence:

- Exploitable official paper closed trades: `455`.
- Official paper net PnL: `-21.397803 EUR`.
- Skipped old closing rows without `realized_pnl`: `100`.

## Top-14 Replay Matrix

Command:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m autobot.v2.cli matrix --run-id vps_2026_06_04_top14 --preset autobot-top14-eur --data-source autobot_state_db --data-path <snapshot_db> --output-dir reports/research/vps_2026_06_04_top14 --include-regime-context --standard-reports
```

Result:

- Cells: `42`
- Success: `42`
- Errors: `0`
- Decisions: `27 reject`, `15 keep_testing`
- No cell met validation criteria.
- Best non-zero replay result: `BTCZEUR / trend`, `6` trades, `-1.270525 EUR`, PF `0.302640`.
- Best PF with non-zero trades: `LINKEUR / trend`, `20` trades, `-4.645811 EUR`, PF `0.507381`.
- Worst replay result: `XLMZEUR / grid`, `265` trades, `-109.914138 EUR`, PF `0.241679`.

Interpretation: on the fresh VPS market sample, the current replayed strategy families do not show validated profitability after costs.

## Paper vs Research Comparison

Corrected command:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m autobot.v2.cli compare-paper-research --run-id vps_2026_06_04_paper_vs_research_fixed --matrix-path reports/research/vps_2026_06_04_top14/vps_2026_06_04_top14.json --state-db <snapshot_db> --output-dir reports/research/vps_2026_06_04_paper_vs_research_fixed
```

Corrected result:

- Paper trades: `455`
- Paper net PnL: `-21.397803 EUR`
- Research trades: `2603`
- Research net PnL: `-1454.810159 EUR`
- Buckets: `56`
- Divergent buckets: `55`

Main limitation: historical official paper trades are still bucketed as `unknown` strategy because older ledger rows lack reliable linked strategy/decision identifiers. This is a measurement gap, not live permission.

## Recent Decision Behavior

Since `2026-06-01T00:00:00+00:00`, recent decision causes include:

- `signal_rejected / microstructure_filter`: `31`
- `buy_rejected / cost_guard`: `21`
- `buy_rejected / opportunity_selection`: `10`

Recent `signal_outcomes` show the rejection learning layer is active. Many BCHEUR/DOTEUR rejections were correctly classified as `saved_loss`, while some `microstructure_filter` decisions produced `missed_profit`. This means the system is learning from rejected signals, but it is not currently producing fresh official paper executions.

## Verdict

AUTOBOT is alive and observing, but the official paper trading ledger is stale. The corrected evidence does not support any claim of current paper profitability.

Recommended next action:

1. Investigate why runtime logs repeatedly show `observe_only` / `router_selected_no_trade` while official paper trades stopped after `2026-05-21`.
2. Add a compact daily runner that produces this same snapshot/matrix/comparison without the heavy per-cell report bundle.
3. Improve strategy attribution for old/new paper ledger rows so future comparisons do not fall into `unknown`.
4. Keep live disabled until fresh official paper execution and replay/research evidence converge positively.
