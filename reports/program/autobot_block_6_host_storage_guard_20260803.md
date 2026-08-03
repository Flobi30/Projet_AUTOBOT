# AUTOBOT Block 6 — Host Storage Guard — 2026-08-03

## Decision

`GO` for the research/shadow operational guard.  This change does not alter
strategy research, shadow observations, paper capital, live execution, sizing,
leverage or order routing.

## Trigger and observed state

The VPS root filesystem reached 85% use, with roughly 12 GB free.  The
AUTOBOT repository data used approximately 3.8 GB; the material source of
pressure was unused Docker build cache rather than research data:

| Category | Before bounded maintenance |
| --- | ---: |
| Docker images | 39.55 GB total, 36.17 GB reclaimable |
| Docker build cache | 49.44 GB total, 47.89 GB reclaimable |
| Root filesystem free space | approximately 12 GB |

No files below `/var/lib/containerd` or `/var/lib/docker` were deleted
directly.  After confirming that no build was active and that the isolated
collector had completed, the following bounded host maintenance succeeded:

```text
docker builder prune --all --force --filter 'until=168h'
docker container prune --force --filter 'until=168h'
```

The root filesystem then had approximately 55 GB free (24% used), the
`autobot-v2` container remained `running healthy`, and recent logs contained
no critical failure or live-order indication.

## Guard added

1. `deploy/rebuild-autobot-image.sh` now refuses a provenance build when free
   space is below 16 GiB.  It performs no automatic cleanup, so a deployment
   cannot silently remove Docker, journal or research artifacts.
2. The isolated runtime-resilience systemd audit uses the same 16 GiB minimum
   and therefore emits the existing fail-closed disk incident before the host
   is too constrained for a controlled rebuild or recovery drill.
3. The research/shadow incident runbook documents read-only inspection and the
   bounded cache maintenance command.  It explicitly forbids manual deletion
   of containerd or Docker storage paths.

## Validation

| Check | Result |
| --- | --- |
| Focused provenance/resilience tests | 16 passed |
| Full suite | 2108 passed, 6 skipped, 2 deselected |
| Python compilation | passed |
| Shell syntax (`rebuild`, verifier, resilience audit) | passed |
| `git diff --check` | passed |
| Low-space preflight test | rejects before Git or Docker is invoked |

## Safety confirmation

- Programme execution lock remains required.
- Observation-only runtime remains required.
- Paper capital, real-order mutation, live trading and automatic promotion
  remain disabled.
- The storage audit and the rebuild preflight contain no exchange client,
  secret access, router import or order path.

## Residual risk

The guard detects low disk space and blocks a future build, but it does not
replace a human-approved retention policy for encrypted off-VPS backups.  The
layer therefore remains `PARTIAL` and the paper-readiness dossier remains
expected to fail closed until all required evidence is verified.
