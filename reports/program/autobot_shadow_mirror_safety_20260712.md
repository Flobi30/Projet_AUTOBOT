# AUTOBOT — Shadow-to-paper mirror safety (2026-07-12)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

## Delivered

- `PAPER_EXECUTION_ADAPTER_ENABLED` now defaults to `false` in code and the
  example environment.
- The retained shadow-to-paper bridge cannot claim that an entry or exit was
  handled unless the instance position count actually changed.
- When the direct-entry guard blocks an entry, the bridge propagates the
  observable refusal and optional shadow contract preview instead of recording
  a false paper entry.

## Scope

No paper capital, live trading, promotion, sizing, leverage, order endpoint,
or UI behavior was enabled. The bridge remains code-present only so it can be
migrated later through the v1 contracts.

## Remaining work

The official paper engine, runtime portfolio/risk routing, and OMS are still
partial. This change removes a misleading execution path; it does not make the
paper model suitable for capital.
