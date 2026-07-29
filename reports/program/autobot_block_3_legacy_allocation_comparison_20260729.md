# AUTOBOT Block 3 — legacy allocation comparison — 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`.

The existing contract-driven portfolio path is kept separate from the legacy
runtime allocator. This increment makes any economic divergence measurable;
it does not replace, mutate, or enable the legacy allocation path.

## Scope delivered

- Added a pure research-only comparator between an immutable
  `TargetPortfolio` and explicit legacy allocation facts.
- The comparison reports canonical and legacy notionals, reserve cash, symbol
  additions/removals and per-symbol deltas.
- Ambiguous symbols, negative/invalid economic values and implicit mapping are
  rejected instead of normalized into a tradeable plan.
- The comparator statically excludes the legacy allocator, orchestrator,
  router, signal handler and paper engine.
- The contract-shadow boundary test now also rejects future imports of the
  legacy allocator.

## Evidence and tests

- portfolio/capacity/sizing/simulator/contract-comparison suite: `57 passed`;
- `python -m py_compile` for the new comparator: passed.

## Safety invariants preserved

- comparison output is research-only and cannot allocate capital, create an
  intent, submit an order, or alter a runtime plan;
- no paper capital, live, promotion, sizing rule, leverage or runtime flag
  changed;
- no execution path, private API, service, database or VPS was called;
- any legacy/canonical disagreement remains `DIVERGENCE_REVIEW_REQUIRED` for
  later human/research analysis rather than an automatic migration.

## Remaining gate

The legacy runtime allocator remains unsuitable as a future paper/live source
until it is replaced by a separately validated canonical portfolio consumer.
The new comparator provides evidence for that future migration without
creating a bridge into the runtime.

## VPS deployment status

Hetzner maintenance prevents controlled deployment. This change is local and
GitHub-only until the VPS can be fast-forwarded, rebuilt through
`deploy/rebuild-autobot-image.sh`, and checked with
`deploy/verify-autobot-runtime-evidence.sh`.
