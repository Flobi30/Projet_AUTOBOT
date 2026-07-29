# AUTOBOT - Bloc 6 - Legacy private-client quarantine - 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`

The local source audit found no active runtime use of the old synchronous
orchestrator or its trading instance. Two legacy capital-lookup helpers still
contained direct private Kraken-client construction, however. They are now
explicitly quarantined before they can create a private client.

## Changes

- The asynchronous legacy capital lookup calls the central observation-only
  private-component guard before reading credentials or building a client.
- The synchronous legacy capital lookup calls the permanent legacy-runtime
  retirement guard before it can import or construct a private client.
- Regression tests prove both helpers fail before their respective private
  path can run.

## Evidence

- Targeted execution, retirement and router suite: `63 passed`.
- `python -m compileall -q` for both orchestrators: passed.
- Full local non-regression: `1992 passed, 6 skipped, 2 deselected`.
- `git diff --check`: passed.

## Safety

- No order, paper capital, live trading, promotion, sizing or leverage change.
- No credential, secret or private endpoint was used by this work.
- Hetzner maintenance still blocks deployment evidence; no VPS action was
  attempted.
