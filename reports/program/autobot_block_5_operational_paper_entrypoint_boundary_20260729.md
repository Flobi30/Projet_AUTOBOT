# AUTOBOT Block 5 — Operational Paper Entrypoint Boundary

## Finding

The retained paper simulator is needed for hermetic unit tests, but two legacy
operational convenience entry points could construct a simulated wallet and
write a paper SQLite database without checking the active observation-only
deployment lock.

## Change

`OrderExecutorAsyncWithPaper(paper_mode=True)` and `get_paper_executor()` now
require the complete explicit paper-execution authorization. In the current
programme this authorization is absent, so both fail closed before a paper
wallet, SQLite database, router or order path exists.

The direct simulator remains available only as a test/research implementation
detail. It is not an operational authorization path.

## Validation

Boundary tests prove both operational entry points reject observation-only
runtime and leave no paper database behind. The regression suite is run before
commit.

## Deployment

Hetzner maintenance is active. No VPS access, service restart, deployment,
runtime database or flag change is attempted for this local hardening.
