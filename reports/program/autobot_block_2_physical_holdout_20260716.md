# AUTOBOT Block 2 — Physical Holdout Gate

## Decision

GO for the research-only implementation. This change does not create a
strategy, activate paper capital, enable live trading or change runtime order
paths.

## Delivered evidence boundary

- A canonical spot snapshot can now be split into deterministic,
  point-in-time `optimization` and `holdout_review` roots.
- Rows missing an `ingestion_time`, or violating event/availability ordering,
  are excluded rather than treated as valid historical proof.
- Each root has a separate canonical source manifest and fingerprint.
- A feature snapshot used by an experiment with a holdout must prove that it
  was materialized from the sealed optimization root; declared matching ids are
  insufficient.
- The final review verifies the sealed holdout root, experiment binding,
  reservation and fingerprinted result artifact before it is recorded.
- A final review is append-only and can be recorded once per experiment.
- Grid and all execution flags remain outside this research-only path.

## Remaining gate

No production holdout has been materialized from the current runtime history.
Creating one requires sufficient canonical rows with known ingestion time and
a deliberate boundary date. Derivatives still require their own physical
point-in-time partition before they can take part in a final holdout review.

## Required validation

- Focused contract, registry, CLI, feature and governance tests.
- Research/paper/governance regression suite.
- Full repository regression suite.
- Controlled VPS rebuild and health check after commit.
