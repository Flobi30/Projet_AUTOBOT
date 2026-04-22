# Freeze Evidence Report

- **Commit SHA:** f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb
- **Timestamp (UTC):** 2026-04-22T01:46:00Z
- **Artifact root:** `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/`

## Exact command / lane list

1. `pytest -q -m "unit and not external and not e2e" --junitxml="artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/junit-unit.xml"`
2. `pytest -q -m "integration and not external and not e2e" --junitxml="artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/junit-integration.xml"`
3. `(cd dashboard && npm run lint)`
4. `(cd dashboard && npm run test -- --reporter=verbose)`
5. `(cd dashboard && npm run build)`
6. Freeze verdict review rerun: `pytest -q tests/test_orchestrator_services_scalability.py`

## Lane outcomes

- **python-tests: unit marker** → **FAIL** (exit code 2; import/collection errors, `ModuleNotFoundError: autobot`).
- **python-tests: integration marker** → **FAIL** (exit code 2; import/collection errors, `ModuleNotFoundError: autobot`).
- **dashboard lint** → **FAIL** (exit code 1; ESLint violations).
- **dashboard test** → **PASS** (exit code 0).
- **dashboard build** → **PASS** (exit code 0; chunk-size warning only).
- **freeze verdict review** → **FAIL** (exit code 2; import/collection error on scalability test module).

## Skipped lanes

- None.

## Artifact inventory

- Python logs + JUnit:
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/pytest-unit.log`
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/junit-unit.xml`
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/pytest-integration.log`
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/python-tests/junit-integration.xml`
- Dashboard logs:
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/dashboard/lint.log`
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/dashboard/test.log`
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/dashboard/build.log`
- Freeze review log:
  - `artifacts/validation/f6fdefe4f7cbce59e57dd316adf21ba844a7b7eb/freeze-review/freeze-verdict-review.log`
