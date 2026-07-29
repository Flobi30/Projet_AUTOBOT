# AUTOBOT Block 6 — Fail-Closed Contract Integrity — 2026-07-29

## Decision

**GO — local resilience hardening.** This change is limited to the
side-effect-free research control-plane contracts. It does not execute a
recovery action or alter any runtime flag.

## Finding

The standard fail-closed helpers calculated the right action, but their public
data objects accepted manually constructed actions or recovery plans weaker
than the incident they claimed to describe. This made a malformed external
object ambiguous even though the normal factory was safe.

## Change

- `IncidentDecision` requires an action at least as severe as its incident and
  a non-empty reason.
- `FailClosedIncidentSummary` cannot understate the strictest incident.
- `FailClosedRecoveryPlan` cannot omit a control step required by any declared
  incident and cannot end below the required terminal action.

## Safety

- The module remains hermetic and has no execution/router/paper imports.
- No order, cancellation, position reduction, paper capital, live routing,
  sizing, leverage, scheduler or dashboard behavior was changed.
- VPS validation is deferred while Hetzner maintenance prevents controlled
  deployment evidence.

## Required validation

Run resilience, kill-switch, cold-restart and CLI tests, then the full suite,
diff check and secret scan before commit. Deploy only through the prescribed
rebuild and evidence scripts after maintenance ends.
