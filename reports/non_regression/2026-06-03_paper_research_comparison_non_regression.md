# Non-Regression - Paper vs Research Comparison - 2026-06-03

Verdict: PASS

## Scope

This change adds a read-only comparison layer between official paper evidence
and research matrix evidence.

New capability:

- compare a matrix JSON report with an official paper source;
- normalize strategy names (`grid` -> `dynamic_grid`, `trend` ->
  `trend_momentum`);
- summarize evidence by strategy/symbol bucket;
- flag divergence between paper and research;
- write JSON/Markdown reports for human review.

## Files Changed

- `src/autobot/v2/research/paper_research_comparison.py`
  - New read-only comparison module.
  - Produces bucket-level paper/research alignment.
  - Uses `MetricsEngine` for paper `TradeJournal` metrics.
  - Reuses existing `MatrixRunResult` contracts.

- `src/autobot/v2/cli.py`
  - Adds `compare-paper-research`.
  - Accepts exactly one paper source:
    `--journal-path`, `--state-db`, or `--paper-trades-db`.
  - Loads matrix JSON with the existing matrix loader.
  - Writes comparison reports unless `--no-write-report` is used.

- `tests/research/test_paper_research_comparison.py`
  - Covers paper/research divergence detection.
  - Covers missing research coverage detection.
  - Covers report writing.

- `tests/test_v2_cli.py`
  - Covers the new CLI command and verifies live remains blocked.

- `docs/research/CLI_WORKFLOWS.md`
  - Documents how to run the comparison after a top-14 matrix.

## What Must Not Have Changed

- Dashboard: unchanged.
- Runtime paper executor: unchanged.
- Kraken/live execution: unchanged.
- Strategy router: unchanged.
- Risk sizing/risk thresholds: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent runtime data: unchanged.

## Trading Safety

- No live trading flag was changed.
- No order execution path was changed.
- No risk, sizing, leverage, fee, spread, slippage, or cost-guard behavior was
  changed.
- The comparison command opens paper sources through read-only loaders where
  applicable.
- The comparison command does not mutate the strategy registry.
- The comparison command does not authorize paper or live promotion.

## Validation

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\paper_research_comparison.py src\autobot\v2\cli.py tests\research\test_paper_research_comparison.py tests\test_v2_cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_paper_research_comparison.py tests\test_v2_cli.py -q
```

Result: `13 passed in 0.31s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk tests\paper tests\test_v2_cli.py -q
```

Result: `109 passed in 0.72s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Runtime / VPS

No VPS restart was performed because this is an isolated research/reporting
change. It does not alter Docker, runtime services, dashboard APIs, paper
execution, live execution, or databases.

## Risks Remaining

- The comparison depends on consistent strategy identifiers in paper decisions.
  Unknown paper strategies are kept as `unknown` rather than guessed.
- Research matrices and paper ledgers must cover comparable time windows for
  the result to be meaningful.
- Divergence is diagnostic evidence, not an automatic strategy decision.

## Recommendation

Run this comparison on the next fresh VPS state snapshot after generating the
standard top-14 matrix. Prioritize buckets where paper and research disagree,
because those indicate either execution/router gaps or research adapter gaps.
