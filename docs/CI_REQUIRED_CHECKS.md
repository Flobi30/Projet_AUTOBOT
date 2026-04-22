# CI checks required before merge (critical branches)

For pull requests targeting critical branches (`main`, `master`, `work`), require the following status check in GitHub branch protection:

- `Required CI gates (critical branches)`

This gate depends on:

- `Conflict marker scan` (job id: `conflict-marker-scan` in `.github/workflows/security-and-audit.yml`).
- `Python tests (unit)` and `Python tests (integration)` from the `python-tests` matrix job.
- `Dashboard build and lint` (job id: `dashboard-build-lint`).

Recommended GitHub configuration:

1. Go to **Settings → Branches**.
2. Add (or edit) protection rules for `main`, `master`, `work`.
3. Enable **Require status checks to pass before merging**.
4. Mark `Required CI gates (critical branches)` as required.

Artifacts are published for diagnostics even when jobs fail.

## Single source of truth

To avoid drift between documentation and CI behavior:

1. Treat `.github/workflows/security-and-audit.yml` as the authoritative source for required gate wiring.
2. Keep `required-critical-gates.needs` synchronized with this document using exact job ids:
   - `conflict-marker-scan`
   - `python-tests`
   - `dashboard-build-lint`
3. Keep the human-readable job name `Required CI gates (critical branches)` listed as the required status check in branch protection.
4. If a required job is moved to another workflow, create a dedicated aggregator in that target workflow and update this file in the same PR.


Additionally, enforce the dedicated pre-merge routine described in `docs/PRE_MERGE_ROUTINE.md`.
