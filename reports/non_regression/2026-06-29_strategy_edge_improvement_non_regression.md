# Strategy Edge Improvement Non-Regression - 2026-06-29

Verdict: PASS

## Scope

Research-only strategy edge triage and improvement reporting.

No runtime trading behavior was changed:

- no live activation;
- no official paper promotion;
- no order creation path;
- no runtime router change;
- no runtime sizing/risk change;
- no instance split/child creation.

## Files Modified

- `src/autobot/v2/research/strategy_edge_improvement.py`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/__init__.py`
- `tests/research/test_strategy_edge_improvement.py`
- `tests/test_v2_cli.py`
- `reports/research/strategy_edge_review_2026_06_29.md`
- `reports/research/strategy_edge_improvement_2026_06_29.md`
- `reports/research/strategy_edge_improvement_2026_06_29.json`

## Logic Added

- `strategy-edge-review` CLI command.
- Research-only triage for:
  - High Conviction;
  - Trend Momentum;
  - Mean Reversion;
  - Relative Value;
  - Grid.
- High Conviction pair attribution.
- Leave-one-symbol-out contribution review.
- Research-only pair quarantine recommendations.
- Trend Momentum redesign checklist.
- Mean Reversion cost-aware review checklist.
- Candidate family discovery plan.

## Tests Run

```text
python -m py_compile src/autobot/v2/research/strategy_edge_improvement.py src/autobot/v2/cli.py src/autobot/v2/research/__init__.py
```

Result: PASS

```text
python -m compileall -q src
```

Result: PASS

```text
$env:PYTHONPATH='src'; python -m pytest tests/research/test_strategy_edge_improvement.py -q
```

Result: 3 passed

```text
$env:PYTHONPATH='src'; python -m pytest tests/test_v2_cli.py::test_cli_strategy_edge_review_writes_research_only_reports -q
```

Result: 1 passed

```text
$env:PYTHONPATH='src'; python -m pytest tests/research/test_strategy_edge_improvement.py tests/research/test_strategy_orchestrator.py tests/test_v2_cli.py::test_cli_strategy_edge_review_writes_research_only_reports -q
```

Result: 17 passed

```text
$env:PYTHONPATH='src'; python -m pytest tests/research tests/test_v2_cli.py -q
```

Result: 229 passed

## Research Report Output

Generated from latest VPS research JSON snapshots copied read-only:

- `reports/research/strategy_edge_review_2026_06_29.md`
- `reports/research/strategy_edge_improvement_2026_06_29.md`
- `reports/research/strategy_edge_improvement_2026_06_29.json`

Key result:

- High Conviction remains `active_research_keep_testing`.
- Trend Momentum remains `research_signal_only / no_capital / redesign_required`.
- Mean Reversion remains `research_signal_only / cost_aware_review_required`.
- Relative Value remains `no_go / no_capital`.
- Grid remains `archived / no_go`.
- No strategy is promoted.
- AVAXEUR and XLMZEUR are research-only quarantine candidates.
- BCHEUR is a concentration watch, not proof of robustness.

## VPS Read-Only Runtime Check

VPS commit: `c4cd491`

Container:

```text
autobot-v2 Up 2 days (healthy)
```

Health:

```json
{"status":"healthy","components":{"orchestrator":"running","websocket":"connected","instances":14}}
```

Flags:

```text
PAPER_TRADING=true
LIVE_TRADING_CONFIRMATION=false
COLONY_AUTO_LIVE_PROMOTION=false
STRATEGY_ROUTER_LIVE_ENABLED=false
```

Read-only SQLite check:

```json
[
  {
    "db": "/opt/Projet_AUTOBOT/data/autobot_state.db",
    "tables": {
      "decision_ledger": {"total": 16395, "recent24h": 1148},
      "orders": {"total": 5811, "recent24h": 0},
      "trade_ledger": {"total": 1142, "recent24h": 0}
    }
  }
]
```

Recent critical logs:

```text
No recent critical/traceback/live-order lines found in the last 300 container log lines.
```

## Trading Safety Confirmation

- live trading enabled: false
- live confirmation enabled: false
- official paper trades created by this patch: false
- runtime router modified: false
- runtime sizing/risk modified: false
- Kraken order submitted: false
- strategy promotion created: false
- instance split executor enabled: false
- real child instance created: false

## Risks / Warnings

- The report is only as good as the latest research snapshots available.
- Trend Momentum and Mean Reversion are currently triaged from orchestrator evidence; they still need dedicated redesign/backtest runs before any capital allocation.
- High Conviction is positive but not robust: only 45 trades, 2/8 positive folds, PF around 1.10 under stress, and heavy BCHEUR concentration.
- Pair quarantine recommendations are research-only and do not modify runtime behavior.

## Next Step

Run targeted research-only redesign experiments:

1. High Conviction with pair attribution and temporary research-only quarantine for AVAXEUR/XLMZEUR.
2. Trend Momentum redesign filters before any simulated capital.
3. Mean Reversion range-only and TP-above-cost review.
4. Add family-level attribution to High Conviction walk-forward outputs before adding heavier strategy layers.

