# AUTOBOT Block 3 — Multi-Signal Portfolio Shadow Review

## Decision

`GO_LOCAL_ONLY` — a new isolated review now evaluates a complete research
portfolio before any order-oriented boundary. It remains strictly research and
shadow only. Paper capital, live, promotion, sizing rules and runtime order
paths were not changed.

## Scope

`src/autobot/v2/research/portfolio_shadow_review.py` adds:

```text
AlphaSignal[]
→ TargetPortfolio
→ per accepted signal pessimistic-cost review
→ per final exposure point-in-time capacity review
→ PortfolioShadowReview
```

The review is deterministic for a fixed input set. It first records target
rejections, then requires every accepted signal to pass the existing shared
pessimistic cost scenario. It evaluates capacity only after the final target
weights and correlation/turnover constraints have been applied.

## Safety invariants

- `PORTFOLIO_SHADOW_READY` is non-executable evidence, not an authorization.
- All output flags are enforced as `research_only=true`,
  `paper_capital_allowed=false`, `live_allowed=false`.
- One accepted component failing pessimistic costs blocks the whole target.
- One final target market with missing, stale or mismatched capacity evidence
  blocks the whole target.
- Capacity is checked against the final target exposures, not a subset selected
  by a caller.
- Inputs require unique signal identifiers; microstructure evidence requires
  an explicit matching market symbol.
- The module does not construct `OrderIntent`, `OrderEvent`, `FillEvent` or
  `ExecutionCommand`, and imports no router, paper, executor, signal-handler
  or orchestrator module.

## Tests

```text
python -m compileall -q src
PASS

PYTHONPATH=src python -m pytest \
  tests/research/test_portfolio_shadow_review.py \
  tests/research/test_portfolio_construction.py \
  tests/research/test_execution_simulator.py \
  tests/research/test_contract_shadow_pipeline.py -q
52 passed

PYTHONPATH=src python -m pytest -q
2050 passed, 6 skipped, 2 deselected

git diff --check
PASS
```

The focused tests cover deterministic input ordering, per-component
pessimistic cost failure, a missing capacity observation, correlation caps,
duplicate signal identifiers and a static non-execution boundary audit.

## Files

- `src/autobot/v2/research/portfolio_shadow_review.py`
- `tests/research/test_portfolio_shadow_review.py`
- `docs/architecture/AUTOBOT_FOUNDATION.md`
- `docs/architecture/layer_coverage.json`

## Deployment state

The Hetzner VPS remains unavailable during the maintenance/payment interval.
No SSH attempt, deployment, container rebuild, runtime change or data write was
made for this increment. GitHub push is safe to perform; VPS verification and
controlled smoke testing remain deferred until access is restored.

## Remaining gate

Layer 13 remains `PARTIAL`. The review establishes a coherent multi-signal
research gate, but future shadow runtime use still requires the separate
artifact, feature-parity, risk-evidence and deployment gates already defined
by AUTOBOT.
