# Non-Regression Report - RiskManagerV2

Date: 2026-06-03
Scope: isolated strict pre-trade risk contract for research/paper/live-parity validation.
Verdict: PASS_WITH_WARNINGS

## Summary

This change adds `RiskManagerV2`, a side-effect-free risk decision engine. It evaluates proposed trades against portfolio, market-data, exposure, drawdown, daily-loss, leverage, Kelly, and anti-martingale constraints.

It does not submit orders, mutate positions, call Kraken, change the existing `RiskManager`, alter `SignalHandlerAsync` runtime behavior, enable live trading, or change paper execution.

## Files Changed

- `src/autobot/v2/risk/__init__.py`
  - New risk package exports.

- `src/autobot/v2/risk/risk_manager_v2.py`
  - Adds:
    - `RiskManagerV2Config`
    - `RiskPortfolioState`
    - `RiskTradeRequest`
    - `RiskDecision`
    - `RiskManagerV2.evaluate(...)`
  - Default risk settings are conservative:
    - default risk per trade: `0.5%`
    - max risk per trade: `1.0%`
    - max symbol exposure: `20%`
    - max global exposure: `50%`
    - max order notional: `10%`
    - max daily loss: `3%`
    - max drawdown: `10%`
    - no leverage by default
    - Kelly disabled by default
    - no adding to losing positions by default
    - live mode rejected unless explicit `live_human_approved=True`

- `tests/risk/test_risk_manager_v2.py`
  - New unit tests for approval, resizing, caps, blockers, live safety, leverage, Kelly, martingale, invalid stops, and minimum order sizing.

- `src/autobot/v2/tests/test_signal_handler_risk_presets.py`
  - Test-helper fix only. The helper uses `SignalHandlerAsync.__new__`, so it must now set `_cost_edge_profiles`, `_edge_cost_buffer_mult`, and `_volatility_edge_weight` just like the real constructor. Runtime code is unchanged.

## Logic Changed

New logic is isolated in `autobot.v2.risk.risk_manager_v2`.

Existing runtime logic unchanged:

- Existing `risk_manager.py` remains intact.
- `SignalHandlerAsync` runtime code unchanged.
- Existing router/promotion gates unchanged.
- Existing paper executor unchanged.
- Existing dashboard/API unchanged.

## Trading Safety

Confirmed:

- No live trading flag was enabled.
- No Kraken order path was touched.
- `mode="live"` is rejected by default with `live_requires_human_approval`.
- The module returns a `RiskDecision`; it never creates `order_id`, fills, positions, or ledger rows.
- Leverage is rejected by default.
- Kelly sizing is rejected by default.
- Adding to losing positions is rejected by default.
- Notional is capped by risk budget, symbol exposure, global exposure, order cap, and cash.
- No fallback permissive router was introduced.

## Validation Commands

Compile targeted files:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\risk\__init__.py src\autobot\v2\risk\risk_manager_v2.py tests\risk\test_risk_manager_v2.py
```

Result: PASS

RiskManagerV2 tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\risk\test_risk_manager_v2.py -q
```

Initial result: `1 failed, 15 passed`

Cause: one test expected risk budget to cap before symbol exposure. The manager correctly applied symbol exposure first. The test was adjusted to widen symbol/global exposure caps for that specific risk-budget test.

Final result:

```text
16 passed in 0.10s
```

Existing risk tests plus V2:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\risk\test_risk_manager_v2.py src\autobot\v2\tests\test_risk_manager.py src\autobot\v2\tests\test_signal_handler_risk_presets.py -q
```

Initial result: `27 passed, 2 failed`

Cause: existing `test_signal_handler_risk_presets.py` helper constructed `SignalHandlerAsync` with `__new__` and omitted newly required initialized attributes. The helper was fixed; runtime code was not changed.

Final result:

```text
29 passed in 0.43s
```

Research suite plus RiskManagerV2:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk\test_risk_manager_v2.py -q
```

Result:

```text
87 passed in 0.70s
```

Compile all backend source:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Runtime VPS

The VPS/container was not restarted. No runtime service uses `RiskManagerV2` yet unless a future integration explicitly imports it. This is intentional: the roadmap first adds the strict contract and tests before wiring it into paper/runtime paths.

## Risks And Warnings

- `RiskManagerV2` is not yet connected to official paper execution. It is a validated contract, not an active runtime gate yet.
- The default caps are conservative and should be calibrated with official paper evidence before runtime integration.
- If later integrated into runtime, another non-regression pass must verify no live activation, no unexpected sizing expansion, and dashboard/API compatibility.

## Recommendation

Next roadmap step should be a paper/research daily reporting or paper-engine wrapper that can call the same risk contract and produce daily `CONTINUE / PAUSE / DISABLE_STRATEGY` evidence without touching live trading.
