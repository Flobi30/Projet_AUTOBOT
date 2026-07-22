# AUTOBOT Block 4 — Shadow `REDUCE` Fail-Closed

## Decision

**GO — governance hardening.** A stored shadow safety action of `REDUCE`
must not leave a new intent able to reuse the old full-size risk mandate.

## Change

Resolving a registered artifact into a new shadow order-intent reference now
fails closed for `REDUCE`, `DISABLE_NEW_ENTRIES` and `QUARANTINE`.

`REDUCE` consequently requires a new immutable artifact bound to an explicitly
reduced mandate before any further shadow intent can exist. This is more
conservative than pretending that an audit event alone changed sizing.

## Validation

```text
78 passed
python -m py_compile src/autobot/v2/research/shadow_governance.py: passed
git diff --check: passed
```

The suite covers governance, append-only observation evidence, runtime preview
boundaries, canonical feature vectors, simulator provenance and contracts.

## Safety

- Research/shadow only.
- No paper capital, live trading, promotion, sizing or leverage change.
- No runtime router or execution import was added.
