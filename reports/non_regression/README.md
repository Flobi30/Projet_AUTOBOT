# AUTOBOT Non-Regression Rule

This folder is the permanent checkpoint for AUTOBOT non-regression reports.

Rule: after every important modification, before starting the next task, create
or update a short report in this folder:

```text
reports/non_regression/<date_or_commit>_non_regression.md
```

If the verdict is `FAIL`, no new feature work may start until the failure is
fixed or explicitly accepted by the user. If the verdict is
`PASS_WITH_WARNINGS`, the warning and remaining risk must be explained clearly
before continuing.

## Minimum Checklist

### 1. What Changed

- Modified files.
- Modified logic.
- Endpoints/routes touched.
- Critical modules impacted.
- Potential risks.

### 2. What Must Not Have Changed

- Dashboard behavior.
- Paper trading behavior.
- Live safety.
- Strategy router behavior.
- Risk management.
- Existing APIs.
- Docker/VPS behavior.
- Existing configuration.
- Persistent data.

### 3. Tests

- Exact commands.
- Complete results.
- Local/VPS differences.
- Skipped tests.
- Non-blocking warnings.
- Coverage of critical modules.

### 4. Trading Safety

- No unvalidated strategy can go live.
- No real order can be sent without human validation.
- No permissive fallback.
- No promotion gate bypass.
- No silent sizing, leverage, risk, or execution change.

### 5. VPS Runtime

- Container healthy.
- `/health` OK.
- Logs without critical errors.
- Main APIs checked when relevant.
- No restart loop.
- No abnormal behavior detected.

### 6. Report Verdict

Every report must include:

- `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`.
- Evidence.
- Remaining risks.
- Recommended actions.
- Explicit confirmation whether work may continue.

## Template

```markdown
# Non-Regression Report - <date_or_commit>

Date: <YYYY-MM-DD>
Verdict: PASS | PASS_WITH_WARNINGS | FAIL

## Summary

## What Changed

## What Must Not Have Changed

## Tests

## Trading Safety

## VPS Runtime

## Risks Remaining

## Recommendation

Can continue: yes/no, with reason.
```

