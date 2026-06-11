# No-Trade Observability Non-Regression - 2026-06-11

## Verdict

`PASS_WITH_WARNINGS`

The implementation is complete locally and tested. It has not been deployed or restarted on the VPS because the mission explicitly forbids a restart without separate approval.

## Files modified

- `src/autobot/v2/orchestrator_async.py`
- `src/autobot/v2/websocket_async.py`
- `src/autobot/v2/cli.py`
- `src/autobot/v2/research/no_trade_attribution_report.py`
- `src/autobot/v2/research/orphan_position_reconciliation.py`

## Files added

- `src/autobot/v2/governance_observability.py`
- `tests/test_governance_observability.py`
- `tests/test_websocket_observability.py`
- `tests/research/test_no_trade_attribution_report.py`
- `tests/research/test_orphan_position_reconciliation.py`
- reports produced by this mission.

## Behavioral scope

- Governance abstentions are persisted only when the decision changes or every five minutes.
- The observer records no-trade/governance decisions after the governance snapshot is built.
- It does not alter the snapshot, router decision, risk decision or execution mode.
- Research reports read SQLite in read-only mode.
- Orphan reconciliation is dry-run only.
- WebSocket logging is rate-limited without changing message handling.

## Commands and results

```text
python -m compileall -q src
PASS

$env:PYTHONPATH='src'; python -m pytest tests\test_governance_observability.py tests\research\test_no_trade_attribution_report.py tests\research\test_orphan_position_reconciliation.py tests\test_websocket_observability.py -q
6 passed

$env:PYTHONPATH='src'; python -m pytest tests\test_strategy_governance.py tests\test_signal_handler_async_unit.py tests\test_market_data_quality.py tests\test_trading_debug_endpoint.py tests\test_v2_cli.py -q
55 passed

$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
153 passed

$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py tests\test_governance_observability.py tests\test_websocket_observability.py tests\test_strategy_governance.py tests\test_signal_handler_async_unit.py tests\test_market_data_quality.py tests\test_trading_debug_endpoint.py -q
191 passed
```

No tests were skipped in these runs.

## Real snapshot results

- Existing ledger: 3,240 decision rows.
- Existing no-trade/governance rows: zero because the deployed VPS does not yet contain this change.
- Logs over 24 hours: 19,467 `router_selected_no_trade` / governance-block occurrences.
- Existing historical cost-guard rows: 255.
- Existing historical microstructure-filter rows: 509.
- Orphan positions: 5, approximate total notional 4.874665 EUR.
- Orphan positions changed: 0.

## Trading safety confirmation

- No strategy promoted.
- No live flag changed.
- No paper execution enabled.
- No Kraken order created.
- No sizing, leverage, risk or cost threshold changed.
- No duplication or spin-off enabled.
- No position closed, deleted or updated.
- `live_promotion_allowed` remains false in generated observability events and reports.

## Warning and next action

The VPS will continue showing the old ledger gap until these changes are deliberately committed, deployed and the service restarted in a separate approved operation. The safe next step is a code review, then an explicitly authorized deployment with post-restart read-only verification.
