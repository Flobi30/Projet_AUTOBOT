# P18I Canonical Data Non-Regression - 2026-07-10

## Verdict

`PASS_WITH_WARNINGS`

P18I changed only research/data plumbing. No runtime trading, paper capital, live trading, router execution, order path, sizing, leverage, UI, promotion, or shadow activation was changed.

## Files Modified

- `src/autobot/v2/research/canonical_ohlcv_store.py`
- `src/autobot/v2/research/data_capability_scanner.py`
- `src/autobot/v2/research/alpha_hypothesis_scheduler.py`
- `src/autobot/v2/cli.py`
- `tests/research/test_canonical_ohlcv_store.py`
- `tests/research/test_data_capability_scanner.py`
- `tests/research/test_alpha_hypothesis_scheduler.py`
- `reports/research/p18i_canonical_data_derivatives_audit_2026-07-10.md`

## What Changed

- Added a research-only canonical OHLCV snapshot builder.
- Added deterministic deduplication and snapshot fingerprinting.
- Added canonical readiness and derivative readiness fields to the data capability scanner.
- Added scheduler-facing data state for canonical OHLCV, funding, basis, open interest, and liquidations.
- Added CLI command `canonicalize-ohlcv`.
- Added tests for dedupe, idempotence, gaps, timestamps, fingerprint, scanner blockers, and scheduler state.

## What Did Not Change

- Dashboard: unchanged.
- Paper runtime: unchanged.
- Live safety: unchanged.
- Strategy router: unchanged.
- Risk management: unchanged.
- Order execution: unchanged.
- Sizing/leverage: unchanged.
- Strategy promotion: unchanged.
- Grid runtime: remains blocked/no-go.
- Persistent ledgers: not deleted or rewritten.

## Tests

Commands:

```bash
$env:PYTHONPATH='src'; python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py -q
$env:PYTHONPATH='src'; python -m pytest tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\research\test_alpha_hypothesis_runner.py tests\research\test_strategy_risk_mandates.py tests\test_v2_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper tests\research\test_canonical_ohlcv_store.py tests\research\test_data_capability_scanner.py tests\research\test_alpha_hypothesis_scheduler.py tests\test_v2_cli.py -q
```

Result:

- `24 passed`
- `68 passed`
- `123 passed`

## Data Smoke

Canonicalization command:

```bash
$env:PYTHONPATH='src'; python -m autobot.v2.cli canonicalize-ohlcv --run-id p18i_canonical_ohlcv_20260710 --raw-paths data/research --output-dir data/research/canonical/ohlcv --manifest-dir data/research/manifests --quarantine-dir data/research/quarantine --report-dir reports/research/canonical_ohlcv
```

Result:

- snapshot_id: `ohlcv_cc74a0fe4f8170c1`
- fingerprint: `cc74a0fe4f8170c1f0b0ffc89f0b97eb9e847ee440e3ce38223054d496c24fbd`
- raw rows: `362711`
- canonical rows: `166149`
- duplicates removed: `196562`
- final duplicates: `0`
- gaps: `22799`
- quarantine: `0`

## Risks Remaining

- OHLCV period is still short for robust strategy conclusions.
- Gaps remain and must be handled by runners.
- Kraken Spot OHLC public history is bounded; a 6-12 month target likely needs progressive accumulation or a verified external source.
- Funding, basis, open interest, and liquidations remain DATA_MISSING until real feeds are collected and canonicalized.

## Live Safety Confirmation

- No live flag changed.
- No paper capital flag changed.
- No strategy was promoted.
- No order path was imported or called by the new research module.
- No Kraken order was created.

## Recommendation

Proceed to P18J only for a narrowly scoped, disabled-by-default derivative data collector design/prototype. Do not retest rejected OHLCV hypotheses unless canonical data receives a significant new period or a genuinely new template is introduced.
