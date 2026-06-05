# Non-Regression - Paper Ledger Signed Slippage

Date: 2026-06-05  
Base commit before change: `c282a16`  
Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers a read-only accounting/research fix in the official paper ledger loader.

Changed files:

- `src/autobot/v2/paper/ledger_loader.py`
- `tests/paper/test_paper_ledger_loader.py`

No dashboard, API route, strategy router, risk manager, order submission, Kraken client, Docker config, or live trading code was changed.

## What Changed

`load_state_db_paper_ledger()` now treats signed `slippage_bps` consistently with runtime semantics:

- positive `slippage_bps` = adverse slippage, counted in `TradeRecord.slippage_eur`;
- negative `slippage_bps` = favorable slippage, stored in metadata only;
- `gross_pnl_eur` is now `net_pnl_eur + fees_eur`, not `net + fees + absolute slippage`;
- large absolute slippage values are reported as loader warnings with `slippage_bps_anomaly:<position_id>`.

This keeps the canonical paper `TradeJournal` from inflating costs or gross PnL when the runtime recorded a favorable fill.

## What Must Not Have Changed

Confirmed unchanged by scope and diff:

- live trading activation;
- paper order routing and fills;
- strategy router behavior;
- promotion gate/live safety;
- risk/sizing/leverage logic;
- dashboard pages;
- existing API contracts;
- persistent DB contents.

The loader remains read-only and does not mutate runtime state.

## Tests

Commands run locally:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/paper/test_paper_ledger_loader.py tests/research/test_cost_parity_audit.py tests/test_v2_cli.py::test_cli_paper_can_read_state_db_trade_ledger tests/test_v2_cli.py::test_cli_cost_parity_audits_read_only_cost_sources -q
```

Result:

```text
11 passed in 0.47s
```

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/paper tests/research tests/test_v2_cli.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
119 passed in 1.25s
```

```powershell
python -m compileall -q src
```

Result: passed.

`compileall` regenerated tracked `.pyc` files; they were restored to `HEAD` and are not part of this change.

## Snapshot Proof

Source:

`data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`

Read-only loader output after the signed slippage fix:

```text
trade_count=455
decision_count=3234
warnings=126
slippage_anomaly_warnings=21
total_net_pnl_eur=-21.397803
total_gross_pnl_eur=-2.499803
total_fees_eur=18.898
total_adverse_slippage_eur=8.666095
total_favorable_slippage_eur=7.329726
```

Interpretation:

- adverse slippage remains visible as cost evidence;
- favorable slippage is retained as fill-quality metadata;
- favorable fills are no longer counted as adverse slippage cost.

## Trading Safety

Confirmed:

- no strategy status/promotion logic was changed;
- no candidate, learning, or shadow-only strategy can pass live because this change does not touch the promotion gate;
- no order-real or Kraken live path was touched;
- no fallback permissive behavior was added;
- no sizing, leverage, risk, stop, TP, or execution threshold was changed.

## Runtime VPS

Public health check:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","timestamp":"2026-06-05T11:13:55.195839+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":629858.337194}}
```

Docker log check warning:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 root@204.168.251.201 "docker ps ... && docker logs ..."
```

Result:

```text
Permission denied (publickey,password).
```

Because the default SSH key is not accepted in this session, Docker logs were not checked directly. This is why the verdict is `PASS_WITH_WARNINGS` rather than a clean `PASS`.

## Risks Remaining

- Historical runtime rows still contain signed slippage anomalies; this loader only reports them and does not rewrite DB history.
- Other read-only analytics that still use absolute signed slippage directly should be audited next, especially `pnl_causality_audit.py`.
- VPS Docker logs should be checked once the correct SSH key is loaded or selected.

## Recommendation

Safe to commit and push this read-only loader fix. The next step should be to apply the same signed-slippage interpretation to any remaining analytics/reporting modules before using their PnL/cost output for strategy decisions.
