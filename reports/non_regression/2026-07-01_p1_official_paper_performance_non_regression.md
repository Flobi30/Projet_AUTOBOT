# P1 Official Paper Performance Non-Regression - 2026-07-01

## Verdict

PASS_WITH_WARNINGS pending final VPS deployment check.

## Scope

P1 adds an official post-P0 paper performance layer. It reads only attributed
paper `trade_ledger` rows with a valid `strategy_id`, excludes legacy
unattributed rows from official strategy metrics, attaches strategy registry
status and paper-gate blockers, and exposes the result through a backend CLI and
a protected API route.

No visible UI design was changed. No live flag, sizing rule, leverage rule,
strategy parameter, or runtime promotion flag was changed. No new strategy was
added.

## Files Modified

- `Dockerfile`
- `src/autobot/v2/api/dashboard.py`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/official_performance.py`
- `tests/paper/test_official_performance.py`
- `tests/paper/test_paper_ledger_loader.py`
- `tests/test_v2_cli.py`
- `reports/non_regression/2026-07-01_p1_official_paper_performance_non_regression.md`

## Behavior Added

- New backend service: `autobot.v2.paper.official_performance`.
- New CLI command:

```powershell
python -m autobot.v2.cli paper-performance-summary --state-db data/autobot_state.db --registry-path docs/research/strategy_hypotheses.json --run-id <id>
```

- New protected API route:

```text
GET /api/paper/performance-summary
```

- Docker image now includes `docs/research/strategy_hypotheses.json` so the
  container can classify strategies consistently with GitHub/VPS source.

## Official Metrics Rules

- Rows without `strategy_id` are counted as legacy/unattributed audit records
  and excluded from official strategy metrics.
- Retired runtime engines such as Grid are excluded from official strategy
  metrics and shown as disabled via registry status.
- `no_trade_baseline` is reported as a reference only, not an alpha strategy.
- `promotable` is always false in this report; any promotion still requires
  explicit human review and separate gates.
- If a metric is not available, the report keeps the strategy in
  `insufficient_data` or `blocked` instead of inventing values.

## Metrics Exposed

The report includes:

- ranking by strategy;
- blocked strategies and blocker reasons;
- best/worst pairs by strategy;
- metrics by `strategy_id`;
- metrics by `strategy_id + symbol`;
- metrics by `strategy_id + symbol + timeframe`;
- metrics by `strategy_id + symbol + timeframe + regime`;
- net PF, net expectancy, gross PnL, fees, slippage, net PnL, win rate and max
  drawdown.

## Tests

Commands run locally:

```powershell
python -m py_compile src/autobot/v2/paper/official_performance.py src/autobot/v2/paper/ledger_loader.py src/autobot/v2/cli.py src/autobot/v2/api/dashboard.py
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests/paper/test_official_performance.py tests/paper/test_paper_ledger_loader.py tests/test_v2_cli.py::test_cli_paper_performance_summary_reads_official_post_p0_ledger tests/test_pf_phase2.py tests/test_strategy_validation_registry.py tests/test_opportunities_endpoint.py::test_performance_endpoints_use_traceable_trade_ledger -q
```

Results:

- `py_compile`: PASS.
- `compileall`: PASS.
- Focused P1 suite: 37 passed.

## Safety Confirmation

- No live flag changed.
- No Kraken order created.
- No official paper trade created by the new CLI/API.
- No strategy promoted.
- No sizing/risk/leverage change.
- No UI-visible redesign.

## Residual Warnings

- Current VPS historical paper ledger may still contain only legacy
  unattributed closing rows. In that case the report will correctly show
  `official_attributed_trade_count=0` and strategy decisions as
  `insufficient_data` or `blocked`.
- The protected API route requires the dashboard token like the other protected
  dashboard endpoints.
