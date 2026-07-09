# P16 High Conviction Reset - 2026-07-09

## Verdict

P16 identifies `high_conviction_swing` as the only strategy worth prioritizing in research right now. The remaining warning `high_conviction_data_paths_missing` was caused by manual shadow sync runs not passing OHLCV paths, while the daily research runner already generated OHLCV and High Conviction reports.

## High Conviction Diagnosis

- Latest VPS daily OHLCV run: `daily_2026_07_09T00_18_07Z`.
- High Conviction walk-forward report exists and used `159782` deduplicated bars across `13` folds.
- Latest High Conviction portfolio shadow sync report exists.
- Cause of manual warning: `shadow-paper-observations` had no `--high-conviction-data-paths`, so High Conviction replay could not run from manual sync despite existing daily OHLCV data.
- P16 patch: when explicit paths are absent, the High Conviction shadow sync now auto-discovers the latest daily OHLCV directory next to the state DB.

## Latest High Conviction Snapshot

- Latest walk-forward decision: `research_only_keep_testing`.
- Paper/live promotion: `false`.
- Primary aggregate blocker reasons:
  - `insufficient_positive_out_of_sample_folds`
  - `non_positive_net_pnl_after_costs`
  - `profit_factor_below_threshold`
  - `no_automatic_paper_or_live_promotion`
- Latest portfolio shadow replay generated `5` closed trades under the conservative research scenario.
- Latest portfolio result: `PF 0.4773`, `net_pnl_eur -4.9537`, `winrate 20%`, `max_drawdown_pct 1.8144`.

## Strategy Reset Recommendation

- `high_conviction_swing`: priority research, keep collecting and diagnosing with OHLCV paths wired.
- `trend_momentum`: keep as benchmark only; reduce or block shadow if it keeps consuming capacity without positive net edge.
- `mean_reversion`: keep as benchmark/cost-aware comparison only; reduce shadow until it proves positive net edge after costs.
- `grid`: remains archived/no-go/runtime-blocked.
- `opportunity_scoring`: remains a metadata/filter layer, not an alpha strategy.

## Safety

- Research-only change.
- No live activation.
- No paper capital activation.
- No promotion.
- No sizing/leverage change.
- No UI change.
- No Kraken order path changed.

