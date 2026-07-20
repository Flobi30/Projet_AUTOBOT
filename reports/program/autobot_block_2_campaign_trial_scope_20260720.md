# AUTOBOT Block 2 - Campaign-level trial scope - 2026-07-20

## Verdict

**GO - research-validation hardening only.** Multiple-testing correction can
now use the complete crossed candidate surface of an explicit research
campaign, rather than silently limiting itself to one hypothesis identifier.

## Delivered behaviour

- `ExperimentSpec` carries an optional, normalized `research_campaign_id`.
- The append-only registry persists that identifier for new experiments and
  indexes it without rewriting legacy rows.
- A supplied campaign scope counts all `candidate_configuration` trials across
  its material experiments. Parameter, pair, timeframe and regime crossings
  remain represented by the existing deterministic trial plan.
- The bounded coordinator and manifested-experiment CLI derive an explicit
  campaign from the registered template family, then pass the campaign total
  as the DSR trial-count floor.
- Experiments predating this schema retain the existing hypothesis-scoped
  fallback and their material fingerprints remain stable. They are never
  silently assigned to a new campaign or reopened as fresh work.

## Safety boundary

This affects only research statistical evidence. It cannot activate shadow,
paper capital, live trading, promotion, sizing, leverage, or an order path.

## Validation

- Registry, manifested-experiment, bounded-coordinator, and CLI tests:
  `67 passed`.
- The added regression test proves that a second hypothesis in the same
  campaign raises the campaign correction count, while an unlabelled legacy
  experiment remains outside that scope; a schema migration preserves the
  legacy material fingerprint when no campaign is declared.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Residual risk / next gate

Campaign scope is explicit metadata, not an inference that two arbitrary
strategies are economically equivalent. The next Block 2 improvement is to
surface the scope identity and count in every statistical report, then require
the same OOS evidence contract before other strategy families may consume it.
