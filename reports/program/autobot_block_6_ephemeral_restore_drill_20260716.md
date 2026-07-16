# AUTOBOT Block 6 — Ephemeral SQLite restore drill (2026-07-16)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

The CLI now provides `sqlite-ephemeral-restore-drill`, which creates a
read-only-source SQLite snapshot, validates a disposable restore, then removes
the entire temporary workspace.

## Safety invariants

- The runtime source database is opened read-only.
- The backup destination must differ from the source and must not already
  exist; accidental overwrites are refused.
- SQLite connections are explicitly closed before temporary cleanup, including
  on Windows.
- The command emits only research-only evidence and cannot enable paper
  capital, live trading or promotion.
- No retained backup is created by this command.

## Runtime proof

Before this CLI wrapper was added, the same isolated backup/restore primitives
completed against the VPS runtime database with a read-only data mount, no
network and a disposable `512 MiB` temporary filesystem. SQLite integrity,
schema and all table row counts matched; the temporary container was removed.

## Evidence

- Focused resilience/CLI/deployment tests: `49 passed`.
- Full repository suite: `1552 passed, 5 skipped, 1 existing dependency
  deprecation warning`.
- `python -m compileall -q src`: passed.
- `docs/architecture/layer_coverage.json`: parsed successfully.
- `git diff --check`: passed.

## Boundary

This does not replace the disabled persistent backup policy. Encrypted off-VPS
storage, retention and a scheduled persistent backup remain separate operator
decisions.
