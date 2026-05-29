# AUTOBOT Research Governance

This folder turns strategy research into a repeatable process before AUTOBOT
changes trading behavior.

## Files

- `AUTOBOT_RESEARCH_PROTOCOL.md`: how a trading idea moves from source review
  to backtest, shadow, official paper, and later human live review.
- `strategy_hypotheses.json`: machine-readable registry of current strategy
  hypotheses, evidence status, gates, and known risks.
- `STRATEGY_ACCEPTANCE_CRITERIA.md`: objective thresholds for backtest,
  walk-forward, shadow and official paper validation.

## Technical Guard

The registry is enforced by `src/autobot/v2/strategy_validation_registry.py` and
covered by `tests/test_strategy_validation_registry.py`. The paper promotion
gate now also checks that a shadow candidate carries a research workflow status
of `shadow_passed` or `paper_validated` before it can become an official paper
candidate.

## Rule

No new strategy should become official paper execution only because it looks
promising in a small shadow sample. It must pass the documented evidence gates:
sample size, net PnL after costs, profit factor, drawdown, reconciliation, and
human review before any live discussion.

## Current Context

As of 2026-05-29, AUTOBOT is healthy in paper mode but official paper history is
negative overall. Grid remains useful as a sensor, but it is not proven as the
main profit engine. The research process should therefore compare engines
against a no-trade baseline and avoid adding complexity without measured value.
