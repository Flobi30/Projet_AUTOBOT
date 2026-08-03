# AUTOBOT — Research/Shadow Incident Runbook

## Scope and invariant

This runbook applies while AUTOBOT is in research and shadow-only mode. It
does not authorize paper capital, strategy promotion, live trading, leverage,
or order submission.

When the market state, persistence state, or order state is uncertain, the
only permitted direction is lower risk:

```text
NORMAL → BLOCK_NEW_SIGNALS → BLOCK_NEW_ORDERS → CANCEL_OPEN_ORDERS
       → REDUCE_POSITIONS → HALT
```

The current programme has no paper-capital or live mandate. `CANCEL_OPEN_ORDERS`
and `REDUCE_POSITIONS` are future execution controls; do not invoke them by
hand as part of research/shadow operations.

## Routine evidence

The isolated `autobot-runtime-resilience-audit.timer` records read-only
evidence every five minutes. It has no exchange network access, no secrets,
and no order-router import. Its latest evidence is stored beneath:

```text
data/research/reports/runtime_resilience/latest.json
```

For an on-demand read-only audit from the AUTOBOT container:

```text
python -m autobot.v2.cli runtime-resilience-audit \
  --state-db data/autobot_state.db \
  --websocket-status connected \
  --websocket-observed-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

`connected` must include a fresh UTC observation timestamp (60 seconds by
default). Missing, future or stale connected evidence is treated as a
fail-closed `WEBSOCKET_DISCONNECTED` incident. Use `unknown` if there is no
current health evidence.

## Incident response

| Evidence | Required state | Immediate handling |
| --- | --- | --- |
| WebSocket disconnected or exchange API unavailable | `BLOCK_NEW_ORDERS` | Preserve logs and wait for fresh health evidence; do not restart into an execution-enabled mode. |
| Market data stale | `BLOCK_NEW_SIGNALS` | Inspect collector freshness and timestamps. Do not fill gaps with future data or rerun a strategy on guessed data. |
| SQLite locked | `BLOCK_NEW_ORDERS` | Let bounded retry finish. If contention persists, keep the risk envelope blocked and capture an audit snapshot. |
| SQLite corruption, disk full, unknown order, or reconciliation required | `HALT` | Treat persistence or position state as untrusted. Do not resume strategy processing until an independent review completes. |
| Container restart | `BLOCK_NEW_ORDERS` | Re-check health, data freshness, ledger evidence and reconciliation before considering any future execution state. |

### Host storage pressure

The routine resilience audit treats less than **16 GiB** free on the runtime
filesystem as `DISK_FULL` for the future risk envelope.  The controlled image
rebuild helper enforces the same minimum before Docker can allocate new build
layers.  Neither check deletes anything automatically.

When this condition occurs, first confirm that no AUTOBOT rebuild or isolated
research collector is active.  Then inspect the host without printing any
environment values or secrets:

```text
df -h /
docker system df
journalctl --disk-usage
```

If Docker reports old, unused build cache, the bounded maintenance action is:

```text
docker builder prune --all --force --filter 'until=168h'
docker container prune --force --filter 'until=168h'
```

This keeps cache used during the last seven days and does not stop a running
container.  Do **not** delete paths below `/var/lib/containerd` or
`/var/lib/docker` manually.  After maintenance, capture deployment evidence
again and keep the programme execution lock, paper lock and live lock intact.

## SQLite recovery evidence

The routine restore drill is deliberately ephemeral: it opens the runtime
database read-only, creates a temporary backup and restore, verifies integrity,
schema and row counts, then removes both temporary files.

```text
python -m autobot.v2.cli sqlite-ephemeral-restore-drill \
  --source data/autobot_state.db
```

This is a proof of recoverability, not a retained backup policy. The retained
backup service remains disabled until encrypted off-VPS storage, retention and
restore ownership have been explicitly approved.

When an approved retained bundle is eventually created, recovery must begin
with `sqlite-backup-bundle-restore-drill`. The drill rejects a bundle without
its final `.autobot_backup_bundle_durability.json` receipt or whose receipt no
longer matches `manifest.json`; do not attempt a manual runtime restore from a
staging directory or an incomplete bundle.

## Reconciliation and restart

1. Keep paper capital and live disabled.
2. Capture read-only runtime-resilience and OMS/ledger audits.
3. If either audit reports a divergence or uncertain order state, leave the
   envelope halted and create an incident report.
4. Do not delete, rewrite or "repair" ledger rows to make an audit pass.
5. Only an explicit human review can approve a future paper mandate; no
   runbook command changes that rule.

After a controlled rebuild, use the read-only deployment-evidence smoke:

```text
bash deploy/verify-autobot-runtime-evidence.sh
```

It emits one non-secret JSON record only when GitHub/VPS/container commits,
container health, `/health`, WebSocket and all observation-only flags agree.
It never rebuilds, restarts, writes data or calls an order path.

## Evidence required before a human paper review

All of the following are required, in addition to a strategy that independently
passes research gates:

- tested kill-switch behavior;
- clean reconciliation evidence;
- verified restore evidence;
- fresh deployment evidence showing the same commit on GitHub, VPS and
  container, with health/WebSocket checks, the code-level programme execution
  lock confirmed inside the container, and all paper/live/promotion paths
  still disabled;
- a versioned coverage matrix with every required layer `VERIFIED`;
- a generated `READY_FOR_HUMAN_PAPER_REVIEW` dossier.

At the current stage, the dossier is expected to remain
`NOT_READY_FOR_HUMAN_PAPER_REVIEW`. That is a safe and correct result.
