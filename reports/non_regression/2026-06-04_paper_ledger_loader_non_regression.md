# Non-Regression - Paper Ledger Loader - 2026-06-04

## Verdict

`PASS_WITH_WARNINGS`

The code change is scoped to read-only paper ledger measurement. It does not alter strategy logic, router behavior, risk checks, order execution, dashboard endpoints, Docker config, persistent runtime data, or live trading.

Warning: the VPS is healthy, but the official paper trade ledger has no new trade rows after `2026-05-21T10:41:49+00:00`. This is a runtime behavior issue to investigate separately.

## What Changed

Files modified:

- `src/autobot/v2/paper/ledger_loader.py`
- `tests/paper/test_paper_ledger_loader.py`
- `reports/research/vps_2026_06_04_operational_summary.md`
- `reports/non_regression/2026-06-04_paper_ledger_loader_non_regression.md`

Logic changed:

- `load_state_db_paper_ledger()` now skips closing legs where `realized_pnl` is missing.
- The loader records `realized_pnl_missing:<position_or_trade_id>` as a warning.
- A regression test verifies that a missing `realized_pnl` closing leg with an incoherent price does not become a false paper profit.

Endpoints/routes touched: none.

Critical modules impacted: read-only paper ledger loader only.

## What Did Not Change

- Dashboard: unchanged.
- Paper execution runtime: unchanged.
- Live safety: unchanged.
- Strategy router: unchanged.
- Risk management: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent VPS data: unchanged.
- Strategy registry/promotion gates: unchanged.
- Sizing, leverage, risk, execution, cost guard: unchanged.

## Test Evidence

Commands run:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python3.12 -m pytest tests\paper\test_paper_ledger_loader.py tests\research\test_paper_research_comparison.py -q
```

Result:

- `7 passed in 0.17s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python -m pytest tests\paper\test_paper_ledger_loader.py tests\research\test_paper_research_comparison.py tests\test_v2_cli.py -q
```

Result:

- `17 passed in 0.50s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'
python3.12 -m pytest tests\paper\test_paper_ledger_loader.py tests\research\test_paper_research_comparison.py tests\test_v2_cli.py tests\test_quant_validation.py tests\test_trading_debug_endpoint.py -q
```

Result:

- `30 passed`
- Warning only: `StarletteDeprecationWarning` from FastAPI TestClient/httpx compatibility.

```powershell
python3.12 -m py_compile src\autobot\v2\paper\ledger_loader.py tests\paper\test_paper_ledger_loader.py
python3.12 -m compileall -q src
```

Result:

- Passed.

Python environment note:

- The same FastAPI API subset fails under `python 3.11.9` because local `.codex_python_deps` contains a `pydantic_core` build not importable by that interpreter.
- It passes under `python3.12`, so this is an environment mismatch rather than a code regression.

## VPS Runtime Evidence

Command:

```powershell
ssh root@204.168.251.201 "curl -sS http://127.0.0.1:8080/health && cd /opt/Projet_AUTOBOT && docker compose ps"
```

Result:

- `/health`: `healthy`
- Orchestrator: `running`
- Websocket: `connected`
- Instances: `14`
- Container: `autobot-v2` up for about 6 days and `healthy`

Recent logs:

- No live order attempt observed.
- Repeated `observe_only`, `router_selected_no_trade`, `microstructure_filter`, `cost_guard`, and setup optimizer pauses.

## Trading Safety Confirmation

- No strategy was promoted.
- No strategy registry mutation was performed.
- No live trading flag was changed.
- No real Kraken order path was modified.
- No fallback permissive was introduced.
- No sizing, leverage, risk, or execution rule was relaxed.
- The change only prevents missing-PnL ledger rows from being interpreted as reliable paper profit.

## Remaining Risks

- Official paper ledger is stale after `2026-05-21`; the bot is active but mainly observing/rejecting.
- Historical paper trades still often map to `unknown` strategy because old ledger rows lack reliable decision/strategy linkage.
- The full top-14 matrix with the heavy report bundle is slow; a compact daily runner should be added for repeatable smoke validation.

## Next Action

Proceed with investigation of why current runtime remains in `observe_only` / no-trade behavior and why fresh official paper executions are not reaching `trade_ledger`.
