# Block 4 — Runtime Signal Provenance Audit (2026-07-22)

## Decision

**GO — audit boundary added; canonical runtime integration remains blocked.**

This increment makes the legacy runtime provenance gap measurable without
modifying the execution path. It cannot start shadow runtime, create an order,
write a paper trade, promote a strategy, or enable live trading.

## Delivered

- `runtime_signal_provenance_audit.py`: deterministic AST-only inventory of
  `TradingSignal` constructors and the required canonical shadow provenance.
- `audit-runtime-signal-provenance`: research CLI that produces a compact JSON
  audit report outside Git-tracked runtime data.
- Tests covering incomplete, dynamic, retired Grid and statically complete but
  still unverified metadata.

## Baseline result

The current strategy source inventory contains 14 signal constructors.

- Ten belong to retained Grid research sources. They are reported for
  inventory only and excluded from actionable migration counts because Grid is
  retired from execution.
- Two actionable trend BUY producers remain blocked:
  - `trend.py` has local indicator metadata but none of the ten canonical
    provenance fields.
  - `trend_async.py` dynamically expands local indicator metadata, so static
    evidence cannot prove any canonical field.
- No producer is considered shadow-runtime eligible by this audit. Even a
  complete literal key set is only `BUY_PROVENANCE_UNVERIFIED` until the
  immutable artifact, verified feature vector and mandate gates succeed.

## Local validation

```text
python -m py_compile src/autobot/v2/research/runtime_signal_provenance_audit.py src/autobot/v2/cli.py
PYTHONPATH=src python -m pytest \
  tests/research/test_runtime_signal_provenance_audit.py \
  tests/research/test_runtime_shadow_preview.py \
  tests/research/test_shadow_observation_ledger.py \
  tests/test_signal_handler_async_unit.py \
  tests/test_v2_cli.py -q
```

Result: `89 passed`.

Full local regression: `1849 passed, 6 skipped`.

## Safety

- Source parsing only; strategy modules are not imported.
- No scheduler, router, executor, paper engine or runtime handler import.
- Legacy direct BUY execution remains fail-closed.
- Grid remains retired; paper capital, automatic promotion and live remain
  disabled.

## Next gate

Any future runtime-shadow integration must consume a separately verified,
time-aligned canonical publication. It must fail closed rather than synthesise
the missing legacy metadata.
