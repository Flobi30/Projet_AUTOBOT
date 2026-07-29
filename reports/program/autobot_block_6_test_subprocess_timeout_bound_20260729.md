# AUTOBOT Block 6 — Bounded Test Subprocesses (2026-07-29)

## Decision

`GO_LOCAL_ONLY` — the hermetic test harness no longer permits its known child
processes to wait indefinitely. This is test-infrastructure hardening only;
it neither imports nor changes AUTOBOT runtime, deployment, order, paper or
live code.

## Scope

Bound each test-owned subprocess invocation to 30 seconds:

- fake-runtime deployment evidence verifier;
- async entrypoint legacy-import quarantine probe;
- retired operator-entrypoint probe;
- paper-operations CLI probe.

The timeout deliberately raises a test failure if a child process stalls,
leaving the parent test process able to report the failure rather than making
the suite appear permanently stuck.

## Evidence

Local commands from the clean development worktree:

```text
python -m compileall -q src tests
python -m pytest tests/test_deployment_runtime_evidence.py \
  tests/test_async_runtime_legacy_quarantine.py \
  tests/test_legacy_operator_tool_retirement.py \
  src/autobot/v2/tests/test_paper_ops_cli_commands.py -q
git diff --check
```

Results:

- compilation: PASS;
- targeted unit/integration regression: `13 passed`;
- diff check: PASS.

## Safety and deployment

- no VPS/SSH access attempted while the Hetzner server is unavailable;
- no GitHub/VPS/container alignment claim is made for this local commit;
- no runtime flags, sizing, leverage, order path, paper capital, live trading
  or promotion behavior changed;
- Grid remains retired from execution.

## Residual risk

This bounds the known test-launched child processes. It does not claim that a
complete desktop test run cannot be interrupted by the host tool itself, nor
does it replace a later clean CI/VPS validation once the server is available.
The global persistence teardown remains intentionally unchanged in this small
test-only patch and should be addressed only with a dedicated lifecycle test.
