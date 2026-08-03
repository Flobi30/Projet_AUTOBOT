# AUTOBOT Block 3 — Strategy Allocation Attribution (2026-08-03)

## Decision

`GO_LOCAL_ONLY` — the research portfolio now preserves the contribution of
each accepted `AlphaSignal` to a multi-strategy target. The contract remains
non-executable and cannot allocate paper capital or send an order.

## Finding

Portfolio construction already enforced spot-long-only, concentration,
correlation, turnover and capacity boundaries. It aggregated expected edges by
symbol, however, and only retained a set of strategy IDs in the final target.
This prevented accurate attribution when multiple strategies supported the
same market and could incorrectly make retained legacy exposure appear to come
from a new strategy.

## Change

- Added the canonical `PortfolioSignalAttribution` contract.
- `TargetPortfolio` now carries ordered, validated per-signal attributions;
  their aggregate can never exceed the target weight for a market.
- Portfolio construction proportionally records each signal's expected-edge
  share before turnover and the fresh allocation that survives turnover.
- Existing exposure retained because of a turnover limit is intentionally not
  credited to new alpha. A signal can remain accepted with zero new allocation
  when it only informs a reduction or cannot increase exposure.
- The existing capacity review remains the independent guard that rejects a
  target whose source-market identity is absent or inconsistent.

## Verification

```text
python -m compileall -q src tests
python -m pytest tests/test_contracts.py \
  tests/research/test_portfolio_construction.py \
  tests/research/test_portfolio_sizing.py \
  tests/research/test_portfolio_shadow_review.py \
  tests/research/test_strategy_execution_boundary.py \
  tests/research/test_contract_shadow_pipeline.py -q
```

Result: `50 passed`.

The tests cover two strategies on one symbol, deterministic allocation shares,
legacy exposure retained under a turnover cap, excess/unsourced attribution
rejection, capacity identity failures and the unchanged execution boundary.

## Safety

- No router, order, paper-capital, live, promotion, sizing or leverage path
  changed.
- The portfolio remains spot long-only and research-only.
- Grid remains retired/no-go.
- No SSH, VPS, Docker, database or runtime flags were changed while the VPS is
  unavailable.

## Residual Risk

The attribution describes target construction, not realised execution or PnL.
Future paper TCA and independent reconciliation must attribute fills and costs
to these signal records only after a human-approved paper mandate exists.
