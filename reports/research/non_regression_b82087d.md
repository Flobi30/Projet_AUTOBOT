# Non-Regression Audit - b82087d

Date: 2026-05-29

Verdict: PASS_WITH_WARNINGS

Scope: audit of commit `b82087d` before starting the event-driven harness. Two small non-regression hardenings were added afterward and deployed:

- `1b33c71` - blocks unknown engines in the promotion gate and closes the aiosqlite test fixture.
- `31f87e0` - makes `no_trade_baseline` explicitly non-executable and non-live-reviewable.

## 1. Diff Summary For b82087d

`b82087d Add strategy validation workflow guard` changed 17 files, with 1626 insertions and 96 deletions.

| File | Change | Risk |
| --- | --- | --- |
| `.env.example` | Added `STRATEGY_RESEARCH_WORKFLOW_GATE_ENABLED=true`. | Low; safer default, no live enablement. |
| `docs/research/README.md` | Documented the validation gate. | Low; documentation. |
| `docs/research/STRATEGY_ACCEPTANCE_CRITERIA.md` | Added objective strategy acceptance criteria. | Low; documentation. |
| `docs/research/strategy_hypotheses.json` | Added v2 registry, workflow statuses, strategy records, live auto-promotion disabled. | Medium; registry correctness matters, now covered by tests. |
| `reports/research/backtest_audit.md` | Added backtest audit report. | Low; documentation. |
| `reports/strategies/*_validation_report.md` | Added standard strategy validation reports. | Low; documentation. |
| `src/autobot/v2/strategy_validation_registry.py` | New pure validation module for registry and strategy workflow. | Medium; core contract for promotion. |
| `src/autobot/v2/strategy_promotion_gate.py` | Added research workflow gate; requires execution-ready statuses before official paper promotion. | High; promotion safety path. |
| `src/autobot/v2/strategy_router.py` | Propagates `validation_status`, defaults missing status to `learning`. | High; router must fail closed. |
| `tests/test_strategy_router.py` | Added/updated router and promotion gate tests. | Low; tests only. |
| `tests/test_strategy_validation_registry.py` | Added registry/workflow tests. | Low; tests only. |

Risk zones reviewed: router, promotion gate, strategy registry, `strategy_hypotheses.json`, tests.

No Kraken order executor, live order path, API key handling, capital allocation live path, or SignalHandler execution path was loosened by `b82087d`.

## 2. Live Safety Confirmation

Confirmed after audit and hardening:

- `learning` strategies are blocked by `research_validation_status`.
- `candidate` strategies are blocked unless they reach `shadow_passed` or `paper_validated`.
- `shadow_passed` can only be considered for official paper promotion and still needs the metric gate.
- `paper_validated` remains blocked when `paper_mode=False`; live gate result is `not_paper_mode` and `live_enabled=false`.
- Unknown strategy engines are blocked by default after `1b33c71`.
- Invalid registry entries block eligibility after `1b33c71`.
- `no_trade_baseline` cannot authorize paper execution or live review after `31f87e0`.
- Runtime `/health` showing 14 instances does not bypass the gate; these are running workers/symbol routes, not live authorization.

Runtime proof on VPS after deployment:

```text
commit: 31f87e0
/health: healthy, orchestrator=running, websocket=connected, instances=14
/api/strategy-router: passed_symbols=0, blocked_symbols=3
sample route AAVEEUR: validation_status=learning, official_execution_enabled=false
sample route ATOMEUR: validation_status=learning, gate_reason=promotion_gate_failed:research_validation_status
```

No real-order attempt was found in the container log scan after redeploy.

## 3. Local vs VPS Tests

Original observed difference:

- Local command:

```powershell
$env:PYTHONPATH='src'; pytest .\tests\test_strategy_validation_registry.py .\tests\test_strategy_router.py .\tests\test_quant_validation.py .\tests\test_pf_phase2.py -q
```

Original result at `b82087d`: `32 passed`.

- VPS command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py -q
```

Original result at `b82087d`: `17 passed`.

Reason: the VPS command intentionally ran only the registry/router gate tests. The local command also included quant validation and PF phase-2 tests. These tests were absent from the VPS command, not skipped.

After hardening:

- Local:

```powershell
python -m py_compile .\src\autobot\v2\strategy_validation_registry.py .\src\autobot\v2\strategy_promotion_gate.py .\src\autobot\v2\strategy_router.py .\tests\test_pf_phase2.py
$env:PYTHONPATH='src'; pytest .\tests\test_strategy_validation_registry.py .\tests\test_strategy_router.py -q
$env:PYTHONPATH='src'; pytest .\tests\test_strategy_validation_registry.py .\tests\test_strategy_router.py .\tests\test_quant_validation.py .\tests\test_pf_phase2.py -q
python -m compileall -q .\src
```

Result: `21 passed` for targeted gate tests, then `36 passed` for the complete selected non-regression set.

- VPS:

```bash
PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py -q
PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_quant_validation.py tests/test_pf_phase2.py -q
```

Result: `21 passed`, then `36 passed`.

VPS environment note: the full command initially failed during collection because host Python lacked `httpx`, required by `fastapi.testclient`. `httpx==0.28.1` is already pinned in `requirements.txt`, so the VPS test environment was completed by installing the pinned dependency. Recommendation: use a project venv or run tests in a dedicated CI image before the event-driven harness.

Executed tests in the final selected set:

- `tests/test_strategy_validation_registry.py`: 12 tests.
- `tests/test_strategy_router.py`: 9 tests.
- `tests/test_quant_validation.py`: 7 tests.
- `tests/test_pf_phase2.py`: 8 tests.

No skipped tests in this selected set.

## 4. aiosqlite Diagnostic

Source: `tests/test_pf_phase2.py::test_trade_ledger_metrics_profit_factor_expectancy`.

Cause: the test created `StatePersistence`, opened an `aiosqlite` connection, and ended without calling `await p.close()`. The aiosqlite worker thread then tried to post back to an event loop already closed by pytest.

Impact:

- It was a test fixture cleanup issue, not introduced by `b82087d`.
- It could leave test worker threads noisy or flaky.
- It was unlikely to affect long-running paper trading directly because runtime persistence is long-lived, but it still signaled an improper async lifecycle pattern.

Fix applied in `1b33c71`: the test now closes `StatePersistence` in a `finally` block.

Proof: final local and VPS selected full runs are `36 passed` with no aiosqlite warning.

## 5. Targeted Non-Regression Coverage

The final tests prove:

- `learning` strategy blocked.
- `candidate` strategy blocked without `shadow_passed` or `paper_validated`.
- `shadow_passed` can only reach official paper candidate after metric checks.
- `paper_validated` remains blocked in live mode.
- Unknown strategy engine blocked by default.
- Malformed registry entry blocks paper/live eligibility.
- Router does not fall back permissively; weak routes go to `no_trade` or `continue_shadow_learning`.
- `no_trade_baseline` cannot become an executable/live-review strategy.

Direct safety checks after deployment:

```json
{
  "missing_registry_exception": "FileNotFoundError",
  "invalid_registry_blocks": "dynamic_grid:baseline_comparison_missing",
  "unknown_engine_passed": false,
  "unknown_engine_reason": "unknown_strategy_engine",
  "no_trade_can_execute_paper": false,
  "no_trade_can_request_live_review": false
}
```

## 6. Runtime Verification On VPS

Commands executed:

```bash
git pull --ff-only origin master
PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py -q
PYTHONPATH=src python3 -m pytest tests/test_strategy_validation_registry.py tests/test_strategy_router.py tests/test_quant_validation.py tests/test_pf_phase2.py -q
docker compose build autobot
docker compose up -d autobot
curl -sS http://127.0.0.1:8080/health
docker logs --since 3m autobot-v2 | grep -Ei 'error|exception|traceback|critical|addorder|real order|ordre reel|paper_mode=false|live order|kraken add'
```

Results:

- VPS commit: `31f87e0`.
- Docker container: `autobot-v2`, healthy.
- `/health`: healthy, orchestrator running, websocket connected, 14 instances.
- Container logs after redeploy: no error/exception/traceback/critical and no real-order attempt found by scan.
- Strategy router runtime: gate enabled, research workflow enabled, 0 passed symbols, 3 blocked symbols.

Observed warning: recurring `WS backpressure` log entries. This predates the non-regression patch and is not a live safety regression, but should be monitored before adding a heavier event-driven harness.

## 7. Recommendation Before Event-Driven Harness

Proceed, but only after keeping these constraints:

1. Keep live disabled and human approval mandatory.
2. Build the event-driven harness behind tests and fail-closed defaults.
3. Add CI or a pinned VPS test venv so local/VPS dependency drift cannot hide tests again.
4. Keep the promotion gate as a hard boundary; the harness must produce evidence, not permission.
5. Monitor websocket backpressure while adding the harness.

