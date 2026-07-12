# AUTOBOT — Runtime bypass guard: adds and leverage (2026-07-12)

## Decision

`GO_FOR_RESEARCH_SHADOW_ONLY`.

## Delivered

- Legacy pyramiding additions are blocked by default before any position state,
  sizing, or `open_position` call is evaluated.
- Automatic leverage activation is blocked by default before capital or trend
  state is evaluated.
- Dynamic paper-capital reallocation is disabled by default; tests which study
  it must opt in explicitly.
- Both paths now require explicit opt-in flags and remain outside the approved
  route until migrated through portfolio, independent risk, and OMS contracts.

## Scope

No exits are changed. No paper capital, live order, promotion, sizing, or
leverage was enabled. The guards only remove autonomous risk increases from
the current runtime.
