# Local derivatives feature readiness — 2026-07-29

## Decision

`WAITING_FOR_MORE_DATA` for any runtime or shadow use.

The local, public-data-only collection establishes a reproducible research
bundle for funding and same-quote basis. It does **not** establish runtime
parity, open-interest history, a strategy result, paper eligibility, or any
form of execution authority.

## Scope

- Source revision: `54e4003ed29117a6e30695a3d2ad203d8cf8f665`.
- Public Kraken Futures endpoints only; no credentials, private endpoints,
  order route, shadow activation, paper capital, promotion, or live trading.
- Assets: BTC and ETH only.
- Local artifacts remain under ignored `data/research/`; they are not a claim
  about the unavailable VPS and must be collected again there through the
  controlled workflow after service restoration.

## Reproducible local evidence

The bounded collector produced the manifest:

`data/research/manifests/local_basis_backfill_20260729_kraken_futures_derivatives.json`

The following verified source histories were available as of
`2026-07-29T15:28:13Z`:

| Dataset | Coverage | Result |
| --- | --- | --- |
| Funding | 17,614 rows, 2025-07-27 to 2026-07-29 | Historical research input ready |
| Same-quote basis | 2,972 rows, 2026-05-30 to 2026-07-29 | Research input ready; no USD/EUR conversion |
| Open interest | 4 snapshots | Current-only; history is insufficient |

The materialized feature bundle is:

`data/research/manifests/local_basis_features_20260729_derivatives_feature_snapshot.json`

It contains 20,590 feature rows. Funding and basis feature values are ready;
the four open-interest change values remain waiting because 24-hour forward
history does not yet exist.

## Safety gates

The data-capability scan reports `funding_basis` as
`DATA_AVAILABLE_RESEARCH_ONLY`, while the point-in-time feature snapshot is
`WAITING_FOR_MORE_DATA` with these blockers:

- `OPEN_INTEREST_HISTORY_WAITING`
- `DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN`

The second blocker is intentional: historical backfill may support research
only, but cannot prove that a future runtime had the data at the relevant
moment. The collected data must therefore not unlock shadow, paper, promotion,
or live behavior.

`liquidation_cascade` remains `DATA_MISSING`; it still lacks real liquidation
events and order-book depth history.

## Required follow-up after VPS restoration

1. Deploy the already-pushed code through the controlled VPS workflow.
2. Re-run the public, bounded BTC/ETH collection on the VPS; do not copy this
   local runtime data into the server.
3. Allow forward ticker/open-interest capture to accumulate before evaluating
   runtime parity or open-interest-change features.
4. Run only a human-guided `DATA_CHECK` after the resulting manifest has
   enough coverage. No `NET_SMOKE`, shadow, paper, or order path is authorized
   by this report.
