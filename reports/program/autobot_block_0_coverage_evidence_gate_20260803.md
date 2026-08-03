# AUTOBOT — Block 0 coverage-evidence gate — 2026-08-03

## Decision

`GO_RESEARCH_SHADOW_ONLY`.

This increment does not advance any layer to `VERIFIED`.  It prevents a
manual status change from being treated as verification without linked proof.
Paper capital, live trading and automatic promotion remain disabled.

## Delivered

- Coverage matrix schema v2 documents the exact evidence needed for a
  `VERIFIED` row: source commit, code paths, test paths and runtime-evidence
  paths.
- `layer-coverage-audit` validates those paths inside the repository root and
  fail-closes an unproven, mismatched or escaped row to `PARTIAL`.
- `paper-readiness-dossier` now consumes the effective audited statuses rather
  than trusting a static label alone.
- Evidence roots can be resolved in both a local checkout and the runtime
  container layout; no arbitrary host path can be referenced.

## Verification

- Focused resilience/readiness/CLI suite passed.
- Full unit and integration regression suite passed after the core change.
- Python compilation, JSON validation and `git diff --check` passed.
- Regression coverage includes missing evidence, commit mismatch, escaped
  evidence paths and container-like repository-root discovery.

## Residual gates

The current matrix remains deliberately `PARTIAL`.  A future layer may be
declared `VERIFIED` only when the relevant code, reproducible tests and fresh
runtime evidence exist at the exact reviewed source commit.  This control is
not a strategy gate and cannot make an otherwise insufficient strategy,
dataset or operational proof eligible for paper review.

## Safety

- No runtime database or data was modified.
- No public or private market-data collector was run by this change.
- No order, paper-capital path, live path or promotion path was called.
