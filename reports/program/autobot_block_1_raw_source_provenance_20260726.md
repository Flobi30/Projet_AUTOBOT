# AUTOBOT — Bloc 1 raw-source provenance — 2026-07-26

## Decision

`GO_RESEARCH_ONLY`.

Canonical OHLCV snapshots now retain an immutable SHA-256 and byte count for
each raw CSV used to create them. This improves reproducibility of research
data without changing a strategy, signal, scheduler decision, paper engine or
runtime execution path.

## Behaviour

- A canonicalization run hashes every selected raw source before it reads it.
- It hashes the same source set again before publishing its snapshot; a change
  during canonicalization fails closed with `raw_source_changed_during_canonicalization`.
- Raw-source provenance contributes to the canonical snapshot fingerprint.
- A read-only verifier detects a later source-file mutation.
- Legacy manifests without raw-source hashes remain historical research data,
  but return no strengthened provenance proof.

## Validation

- focused canonical/feature/scanner suite: `44 passed`;
- full suite: `1898 passed, 6 skipped, 2 deselected`;
- Python compilation and `git diff --check`: passed.

## Safety

- research-only canonical data path;
- no private endpoint, secret, paper capital, live flag, promotion, sizing,
  leverage, shadow activation or order path is imported or changed;
- Grid remains retired/no-go.

## Remaining boundary

This verifies integrity for snapshots created by the strengthened
canonicalizer. It does not retroactively claim immutable raw provenance for
older snapshots, and does not make historical backfills runtime-parity data.
