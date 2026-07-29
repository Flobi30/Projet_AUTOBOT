# AUTOBOT Block 6 — Program Lock Deployment Evidence — 2026-07-29

## Decision

`REWORK_FOR_VPS_VALIDATION`

The local deployment-evidence boundary is complete.  The VPS has not been
changed while its Hetzner maintenance prevents controlled access, so this
report does not claim VPS or container alignment.

## Change

`deploy/verify-autobot-runtime-evidence.sh` now proves two independent safety
facts before it emits a `RuntimeDeploymentEvidence` record:

1. the fixed non-secret environment safety flags are present; and
2. the running container's code reports the exact fail-closed authorization
   state:
   - `program_execution_locked=true`;
   - `observation_only_runtime=true`;
   - `paper_execution_authorized=false`;
   - `real_order_mutation_authorized=false`.

The probe imports only the pure authorization modules in an already-running
container. It starts no AUTOBOT runtime service, opens no database, reads no
secret, calls no exchange endpoint and cannot create an order.

The exact non-secret readiness schema now includes
`program_execution_locked`. Missing, malformed or false values block the
human paper-readiness dossier. Existing evidence generated before this change
is intentionally stale/incomplete and must be regenerated after deployment.

## Local proof

- Core code commit: `ee39d9c5e073f62d7043ebaaf17dad8a4f9645a5`
- Documentation follow-up: `341611992c031ec6b8381a35bd7f89b2dab41ad6`
- Hermetic verifier-behaviour test: `b35faec1634e38b0865af646c9cefc5fd5304f1b`
- Focused deployment verifier test: `2 passed`
- Full non-regression suite: `2026 passed, 6 skipped, 2 deselected`
- `python -m compileall -q src`: passed
- `bash -n deploy/verify-autobot-runtime-evidence.sh`: passed
- `git diff --check`: passed before commit
- Changed production files secret-pattern scan: passed

## Safety

- No paper capital enabled.
- No live trading enabled.
- No automatic promotion enabled.
- No sizing or leverage changed.
- No order, paper-order, private Kraken endpoint or runtime order path called.
- No VPS, Docker, systemd, database or data mutation was attempted.

## Required VPS follow-up after maintenance

1. Fast-forward `/opt/Projet_AUTOBOT` to current GitHub `master`.
2. Run `bash deploy/rebuild-autobot-image.sh`.
3. Run `bash deploy/verify-autobot-runtime-evidence.sh` and retain its JSON.
4. Verify GitHub/VPS/container alignment, `/health`, WebSocket and instance
   count from the returned evidence and health payload.
5. Confirm the verifier succeeds only with the code-level program lock still
   true and every paper/live/promotion authorization false.

No research collection, NET_SMOKE, shadow, paper, live or order path is part
of this follow-up.
