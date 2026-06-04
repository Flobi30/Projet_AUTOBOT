# Non-Regression - Paper/Research Decision Trace Diagnostics

Verdict: PASS

## Scope

Commit under validation: pending local change after `c9db11e`

Changed files:

- `src/autobot/v2/research/paper_research_comparison.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_paper_research_comparison.py`
- `tests/test_v2_cli.py`

Logic changed:

- The paper/research comparison report can now include read-only decision trace summaries per strategy/symbol bucket.
- `compare-paper-research` can attach a read-only `decision_trace_audit` from `--state-db` automatically, or from optional `--decision-state-db`.
- Bucket diagnostics can now point to missing runtime stages such as `signal`, `order`, `fill`, `trade`, `pnl`, or `outcome`.

Endpoints/routes touched: none.

Critical trading modules touched: none.

## Expected Non-Changes

- Dashboard unchanged.
- Paper trading execution unchanged.
- Live trading execution unchanged.
- Strategy router unchanged.
- Risk management unchanged.
- Sizing, leverage, TP/SL and execution thresholds unchanged.
- Docker/VPS runtime unchanged.
- Persistent runtime data unchanged.

## Trading Safety

- No live order path was modified.
- No Kraken order submission path was modified.
- No strategy promotion gate was modified.
- No fallback permissive behavior was added.
- The new code is report-only and read-only.
- `compare-paper-research` still carries safety notes stating no paper/live order is created and no live permission is granted.

## Tests

Commands run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research\test_paper_research_comparison.py tests\test_v2_cli.py::test_cli_compare_paper_research_reports_divergence tests\test_v2_cli.py::test_cli_compare_paper_research_accepts_validate_strategies_output tests\test_v2_cli.py::test_cli_compare_paper_research_attaches_state_db_decision_trace -q
```

Result:

```text
7 passed in 0.33s
```

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research tests\test_v2_cli.py -q
```

Result:

```text
98 passed in 1.20s
```

Command:

```powershell
$env:PYTHONPATH='src'; python -m compileall -q src
```

Result: PASS

Command:

```powershell
git diff --check
```

Result: PASS, with Windows CRLF warnings only.

Skipped tests: none in the executed suites.

## Runtime VPS

Command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{
  "status": "healthy",
  "components": {
    "orchestrator": "running",
    "websocket": "connected",
    "instances": 14
  }
}
```

No restart was performed. No runtime mutation was performed.

## Risks

- This change can only explain stored traces that are present in `decision_ledger`, `orders`, `trade_ledger`, or `signal_outcomes`. If a runtime table does not store a stage, the report will mark that stage missing.
- The comparison still depends on canonical strategy/symbol mapping quality. Existing canonicalization is used; no new mapping behavior was added here.
- This does not yet unify the official runtime cost model and research cost model; it only makes divergences easier to locate.

## Recommendation

Proceed to the next roadmap step: use these trace diagnostics to prioritize the actual unification work, especially strategy interface, execution cost model, and TradeJournal/MetricsEngine parity.
