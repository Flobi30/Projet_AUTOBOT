# AUTOBOT strategy-artifact readiness snapshot audit

This is a research-governance diagnostic. It verifies temporary SQLite
snapshots, then reports whether immutable research evidence is sufficient for
a **human** to consider registering a non-executable shadow artifact.

It never registers an artifact, starts shadow runtime, writes the paper
ledger, enables paper capital, enables live trading, creates an order, or
changes a strategy status.

## Why snapshot first

The experiment registry can run in SQLite WAL mode. A direct audit of that
live database from an isolated, read-only container may need WAL sidecar files
and can fail or be inconsistent. The command uses SQLite's backup API with a
read-only source connection, audits only a private `/tmp` snapshot, and then
removes the snapshot before the container exits.

If the source cannot be snapshotted safely, the command returns
`SNAPSHOT_UNAVAILABLE`. It never falls back to a direct audit of the live
registry. A transient source checksum change is reported as possible concurrent
runtime activity, not attributed to the audit.

## Local command

```text
python -m autobot.v2.cli strategy-artifact-readiness-snapshot-audit \
  --registry-path data/research/experiment_registry.sqlite3 \
  --artifact-registry-path data/research/strategy_artifacts.sqlite3
```

The caller must have filesystem permission to create a SQLite read-only
snapshot from the source. For WAL sources, use the isolated systemd wrapper
rather than mounting a live database into arbitrary diagnostic containers.

## VPS wrapper

`deploy/systemd/run-autobot-strategy-artifact-readiness-snapshot-audit.sh` is
disabled by default. It starts a disposable Docker container with:

- no network;
- no secrets or runtime-state mount;
- read-only application filesystem;
- a read-only `data/research` source mount;
- a private writable `/tmp` only;
- dropped Linux capabilities and `no-new-privileges`.

The systemd service carries
`AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_ENABLED=false`. Do not enable its
timer automatically. A human operator must decide whether recurring governance
audits and the generated compact report should be retained.

## Interpretation

- `NO_SHADOW_ARTIFACT_CANDIDATE`: do not register or run anything; keep
  collecting/validating research evidence.
- `HUMAN_GOVERNANCE_REQUIRED`: immutable evidence exists, but a separately
  approved risk mandate and human approval are still required. It is not a
  paper or live authorization.
- `SNAPSHOT_UNAVAILABLE`: treat evidence as unavailable and investigate
  storage/WAL access. Do not bypass the snapshot boundary.
