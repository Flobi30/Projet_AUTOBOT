# AUTOBOT Research CLI Workflows

This document records repeatable research commands for AUTOBOT. These workflows
are research-only: they do not start the runtime bot, do not submit Kraken
orders, do not mutate the strategy registry, and do not authorize live trading.

## Standard Top-14 Matrix

Use this workflow when a fresh VPS state database has been copied locally and
the goal is to compare the current research strategy families on the standard
AUTOBOT EUR universe.

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
& '<python3.12.exe>' -m autobot.v2.cli matrix `
  --run-id vps_YYYY_MM_DD_top14 `
  --preset autobot-top14-eur `
  --data-source autobot_state_db `
  --data-path data/vps_autobot_state_YYYY-MM-DD.db `
  --output-dir reports/research/vps_YYYY_MM_DD_top14 `
  --include-regime-context `
  --standard-reports
```

The `autobot-top14-eur` preset expands to:

- `BTCZEUR`
- `ETHZEUR`
- `SOLEUR`
- `LTCZEUR`
- `XLMZEUR`
- `XRPZEUR`
- `TRXEUR`
- `ADAEUR`
- `LINKEUR`
- `DOTEUR`
- `BCHEUR`
- `ATOMEUR`
- `AVAXEUR`
- `AAVEEUR`

The default strategy families are:

- `grid`
- `trend`
- `mean_reversion`

## Standard Reports

`--standard-reports` writes the normal research bundle:

- registry recommendations report;
- loss attribution report;
- setup quality report;
- strategy/regime report;
- strategy/regime baseline report;
- strategy/regime walk-forward report;
- strategy scorecard.

These reports are evidence and recommendations only. They do not update
`docs/research/strategy_hypotheses.json` and do not promote a strategy.

## Narrow Overrides

To debug one symbol or one strategy while keeping the same CLI shape:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
& '<python3.12.exe>' -m autobot.v2.cli matrix `
  --run-id trx_grid_debug `
  --preset autobot-top14-eur `
  --symbols TRXEUR `
  --strategies grid `
  --data-source autobot_state_db `
  --data-path data/vps_autobot_state_YYYY-MM-DD.db `
  --output-dir reports/research/trx_grid_debug `
  --standard-reports
```

Explicit `--symbols` and `--strategies` values override the preset while keeping
the same cost model, safety notes and report layout.

## Paper vs Research Comparison

After running a research matrix from fresh VPS data, compare the official paper
ledger against the research result:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
& '<python3.12.exe>' -m autobot.v2.cli compare-paper-research `
  --run-id vps_YYYY_MM_DD_paper_vs_research `
  --matrix-path reports/research/vps_YYYY_MM_DD_top14/vps_YYYY_MM_DD_top14.json `
  --state-db data/vps_autobot_state_YYYY-MM-DD.db `
  --output-dir reports/research/vps_YYYY_MM_DD_paper_vs_research
```

Optional date filter for daily paper closes:

```powershell
  --report-date YYYY-MM-DD
```

This comparison normalizes strategy names such as `grid` -> `dynamic_grid` and
`trend` -> `trend_momentum`, then compares paper and research by
strategy/symbol bucket. Useful outcomes:

- `aligned_negative`: paper and research both say the bucket is not working;
- `aligned_positive`: paper and research both look positive, but still require
  baselines and walk-forward before any promotion;
- `paper_positive_research_negative`: investigate sample/runtime mismatch;
- `paper_negative_research_positive`: investigate router, execution, fills or
  paper/replay parity gaps;
- `paper_has_trades_research_missing`: research adapters do not cover what
  paper executed;
- `paper_missing_research_has_trades`: paper gates/router blocked what research
  replay expected.

## Safety Checklist

Before using a matrix result as evidence:

- verify net PnL includes fees, spread and slippage;
- verify baseline comparison is present;
- verify out-of-sample or walk-forward evidence exists before promotion;
- verify no result is dominated by one symbol or tiny sample;
- verify `live_promotion_allowed` remains false unless a separate human live
  review has explicitly approved the strategy.
