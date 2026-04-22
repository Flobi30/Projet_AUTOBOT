# CI checks required before merge (critical branches)

For pull requests targeting critical branches (`main`, `master`, `work`), require the following status check in GitHub branch protection:

- `Required CI gates (critical branches)`

This gate depends on:

- `Python tests (unit)` and `Python tests (integration)` from the `python-tests` matrix job.
- `Dashboard build and lint`.
- `Conflict marker scan`.

Recommended GitHub configuration:

1. Go to **Settings → Branches**.
2. Add (or edit) protection rules for `main`, `master`, `work`.
3. Enable **Require status checks to pass before merging**.
4. Mark `Required CI gates (critical branches)` as required.

Artifacts are published for diagnostics even when jobs fail.


Additionally, enforce the dedicated pre-merge routine described in `docs/PRE_MERGE_ROUTINE.md`.
