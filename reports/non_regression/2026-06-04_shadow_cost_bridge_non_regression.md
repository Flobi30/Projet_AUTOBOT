# Non-Regression - Shadow Cost Bridge

Verdict: PASS

## Scope

Commit under validation: pending local change after `6e8fee5`

Changed files:

- `src/autobot/v2/shadow_cost_bridge.py`
- `src/autobot/v2/trend_shadow_lab.py`
- `src/autobot/v2/mean_reversion_shadow_lab.py`
- `src/autobot/v2/setup_shadow_lab.py`
- `src/autobot/v2/shadow_paper_adapter.py`
- `tests/test_shadow_cost_bridge.py`

Logic changed:

- Added a bridge from the research execution cost model to legacy shadow cost fields.
- Default shadow costs now derive from research costs:
  - `fee_bps_per_side = taker_fee_bps`
  - `slippage_bps_per_side = slippage_bps + latency_buffer_bps + fallback_spread_bps / 2`
- Existing shadow environment overrides remain supported.
- Shadow metadata now exposes `effective_cost_bps_per_side` and `cost_model_source`.

Endpoints/routes touched: none.

Critical live trading modules touched: none.

## Expected Non-Changes

- Dashboard unchanged.
- Official paper execution unchanged.
- Live trading execution unchanged.
- Strategy router unchanged.
- Risk management unchanged.
- Sizing/leverage unchanged.
- Kraken order submission unchanged.
- Persistent runtime data unchanged.

## Trading Safety

- No live path was modified.
- No Kraken integration was modified.
- No strategy promotion gate was modified.
- No permissive fallback was added.
- Shadow simulations become more conservative by default because spread and latency are now included in the legacy slippage bucket.
- Environment overrides are still explicit and auditable.

## Tests

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_shadow_cost_bridge.py tests\test_trend_shadow_lab.py tests\test_mean_reversion_shadow_lab.py tests\test_setup_shadow_lab.py -q
```

Result:

```text
14 passed in 0.54s
```

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research tests\paper tests\test_shadow_cost_bridge.py tests\test_trend_shadow_lab.py tests\test_mean_reversion_shadow_lab.py tests\test_setup_shadow_lab.py tests\test_v2_cli.py -q
```

Result:

```text
123 passed in 1.50s
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

- Shadow results may look worse after restart if no custom shadow fee/slippage env vars are set. This is intentional: shadow should not be cheaper than research replay.
- Official paper and live runtime cost models are not changed yet; this step only aligns shadow defaults and metadata.
- Existing databases keep historical shadow results calculated under older assumptions. New rows will be comparable only after the process loads the new code.

## Recommendation

Proceed to the next roadmap step: add a parity audit that compares official paper ledger realized costs, shadow assumptions, and research cost assumptions on fresh VPS data.
