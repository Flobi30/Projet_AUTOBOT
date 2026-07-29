# AUTOBOT Block 6 — SQLite backup publication durability — 2026-07-29

## Decision

**GO — local resilience hardening.** The scheduled retained-backup service
remains disabled and VPS validation remains deferred while Hetzner is
unavailable.

## Finding

The fixed-scope SQLite bundle already captured verified snapshots through a
staging directory and an atomic directory rename. It did not prove that the
snapshot files, manifest, or final directory entry had reached durable storage
before a sudden host interruption.

## Change

- Synchronize each private SQLite snapshot before publishing its filename.
- Synchronize the staged manifest and staging directory before the atomic
  publish step.
- Synchronize the parent directory after the rename.
- Write a final non-secret durability receipt:
  `.autobot_backup_bundle_durability.json`.
- A restore drill now refuses a missing, pending, malformed, or
  manifest-mismatched receipt.
- On Linux, the helper synchronizes directory metadata as well as files. The
  Windows development host records that directory metadata synchronization is
  not independently available through the portable Python interface; it does
  not claim the stronger POSIX guarantee. The production VPS must validate the
  stricter Linux branch after restoration.

If the final publication synchronization fails after the rename, the receipt
is explicitly reverted to its already-synchronized pending state. The bundle
then remains fail-closed and cannot be used by the restore drill.

## Validation

- `python -m pytest tests/research/test_resilience_readiness.py -q` — **30
  passed**.
- `python -m compileall -q src/autobot/v2/research/resilience_readiness.py` —
  passed.
- Added coverage for final receipt creation, missing/pending receipt rejection,
  manifest binding, and a simulated final directory-sync failure.

## Safety

- No VPS, Docker, systemd, runtime flags, databases, secrets, private API,
  paper capital, promotion, live trading, sizing, leverage, or order path was
  touched.
- No backup timer was enabled; no persistent backup was created.

## Required VPS follow-up

After Hetzner access is restored, run the controlled deployment, then an
approved, non-runtime restore drill against a newly created bundle. Confirm
the Linux receipt status is `DURABLE_FILE_AND_DIRECTORY_SYNCED`; leave the
backup timer disabled until the separate encryption, off-VPS retention, and
ownership policy is approved.
