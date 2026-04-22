# Freeze evidence — current head (2026-04-22)

## Scope
Focused freeze-blocker validation for:
- CI workflow dependency consistency (`.github/workflows/security-and-audit.yml`)
- runtime operator log hint alignment (`start-autobot.sh`)
- current-head test evidence for freeze decision

## Head
- Commit under test: `1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1`

## Commands executed and outcomes

1) Workflow dependency graph consistency (all `needs` target existing job ids)

```bash
python - <<'PY' > artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/workflow-needs-check.txt
# static parser of jobs + needs in .github/workflows/security-and-audit.yml
PY
```

- Outcome: **PASS** (`result: PASS`)
- Artifact: `artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/workflow-needs-check.txt`

2) Focused freeze-relevant test: scalability guard

```bash
PYTHONPATH=src pytest -q src/autobot/v2/tests/test_scalability_guard.py \
  --junitxml=artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/junit-scalability-guard.xml
```

- Outcome: **PASS** (`3 passed in 0.30s`)
- Artifacts:
  - `artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/pytest-scalability-guard.log`
  - `artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/junit-scalability-guard.xml`

3) Focused freeze-relevant test: paper ops CLI validation/reporting safety path

```bash
PYTHONPATH=src pytest -q src/autobot/v2/tests/test_paper_ops_cli_commands.py \
  --junitxml=artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/junit-paper-ops-cli.xml
```

- Outcome: **PASS** (`3 passed in 0.64s`)
- Artifacts:
  - `artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/pytest-paper-ops-cli.log`
  - `artifacts/validation/1ee4b7a380ac2b163fc6673f4c1d38b64d89f8a1/freeze-focus/junit-paper-ops-cli.xml`

## Note on broad suite attempt
An initial broad marker-run command was attempted and failed because of unrelated environment/test-collection issues (missing `httpx` and marker hygiene errors in non-freeze focus tests). The freeze decision evidence above therefore uses focused suites tied directly to the blockers and freeze gate behavior.
