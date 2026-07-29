# AUTOBOT Block 4 — Shadow Safety Decision Integrity — 2026-07-29

## Decision

**GO — local governance hardening.** Block 4 remains `PARTIAL`: no runtime
shadow producer is enabled and no paper/live path is changed.

## Finding

`ShadowSafetyDecision` was immutable but did not itself validate the relation
between its action and its next artifact status. The normal factory produced
correct values, but a direct caller could construct a malformed decision such
as `REDUCE -> SHADOW` before presenting it to an append-only registry or to
the artifact transition helper.

## Change

- Decisions now normalize and validate their action.
- Their next status must equal the monotonic policy mapping:
  `NORMAL/WATCH -> SHADOW`, `REDUCE/DISABLE_NEW_ENTRIES -> THROTTLED`,
  `QUARANTINE -> QUARANTINED`.
- Reasons are mandatory and non-empty.
- Risk increase, paper capital, live, and automatic promotion permissions are
  rejected even in an in-memory decision object.

## Safety

- Research/shadow governance only.
- No router, order, paper, sizing, leverage, or runtime activation change.
- The VPS is intentionally untouched while Hetzner maintenance prevents a
  controlled deployment.

## Required local validation

Run the focused governance suite, the full hermetic test suite, `git diff
--check`, and a targeted secret scan before commit. VPS rebuild and smoke
remain pending maintenance completion.
