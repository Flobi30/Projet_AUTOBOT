# Non-Regression - PnL Causality Signed Slippage

Date: 2026-06-05  
Base commit before change: `0173826`  
Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers a read-only analytics correction in the PnL causality audit.

Changed files:

- `src/autobot/v2/pnl_causality_audit.py`
- `tests/test_pnl_causality_audit.py`

No strategy, execution, paper fill, Kraken, risk, sizing, promotion gate, dashboard view, Docker config, or persistent data was changed.

## What Changed

The PnL causality audit now uses signed slippage consistently:

- positive `slippage_bps` is adverse and contributes to `slippage_bps` / `actual_cost_bps`;
- negative `slippage_bps` is favorable and is exposed as `favorable_slippage_bps`;
- `absolute_slippage_bps` remains available for diagnostics/anomaly awareness;
- `slippage_drag` is no longer raised for favorable fills.

The audit query now excludes closing ledger rows where `realized_pnl IS NULL`. These rows are not closed performance evidence and previously inflated the closed-trade count.

## What Must Not Have Changed

Confirmed unchanged by scope and diff:

- live trading activation;
- strategy router and promotion gates;
- order submission and paper execution;
- risk/sizing/leverage thresholds;
- dashboard routing/pages;
- API authentication;
- DB contents.

The module remains read-only.

## Tests

Commands run locally:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_pnl_causality_audit.py tests/paper/test_paper_ledger_loader.py tests/research/test_cost_parity_audit.py -q
```

Result:

```text
13 passed in 0.81s
```

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_pnl_causality_audit.py tests/paper tests/research tests/test_v2_cli.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
123 passed in 1.51s
```

```powershell
python -m compileall -q src
```

Result: passed.

`compileall` regenerated tracked `.pyc` files; they were restored to `HEAD` and are not part of this change.

## Snapshot Proof

Source:

`data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`

Read-only PnL causality audit output after the fix:

```text
summary_closed_trades=455
summary_net_pnl_eur=-21.397803
summary_profit_factor=0.361
summary_avg_fee_bps=33.23
visible_unique_trades=69
visible_adverse_slippage_bps_sum=1922.38
visible_favorable_slippage_bps_sum=464.45
visible_absolute_slippage_bps_sum=2386.83
first_recent={'symbol': 'TRXEUR', 'position_id': '08a5e7cd', 'slippage_bps': 0.0, 'favorable_slippage_bps': 12.7, 'absolute_slippage_bps': 12.7, 'actual_cost_bps': 79.72, 'verdict': 'cost_drag_loss'}
```

Additional DB evidence:

```text
closing_total=555
closing_with_realized_pnl=455
closing_missing_realized_pnl=100
```

Interpretation:

- the audit now matches the canonical loader count of 455 usable closed trades;
- 100 closing rows without realized PnL are no longer treated as zero-PnL closed trades;
- favorable slippage remains visible without becoming cost drag.

## Trading Safety

Confirmed:

- no live execution path was changed;
- no candidate, learning, or shadow strategy can bypass promotion gates because gates were untouched;
- no Kraken order path was touched;
- no permissive fallback was added;
- no sizing, risk, stop, TP, leverage, or threshold was changed.

## Runtime VPS

Public health check:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{"status":"healthy","timestamp":"2026-06-05T11:30:00.644634+00:00","version":"2.0.0","components":{"orchestrator":"running","websocket":"connected","instances":14,"uptime_seconds":630823.785844}}
```

Warning: Docker logs were not checked in this pass because SSH with the default key returned `Permission denied (publickey,password)` during the previous runtime check in this session. This is why the verdict remains `PASS_WITH_WARNINGS`.

## Risks Remaining

- Historical rows without `realized_pnl` still exist in the DB and should remain visible through traceability audits, but not counted as performance.
- Other analytics may still need similar alignment with the canonical paper loader.
- Direct VPS Docker log review should be retried with the correct SSH key selected.

## Recommendation

Safe to commit and push. The next roadmap step should continue aligning all paper performance surfaces around the same canonical closed-trade definition and signed cost semantics.
