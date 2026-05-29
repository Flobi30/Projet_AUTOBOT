# AUTOBOT Research Governance

This folder turns strategy research into a repeatable process before AUTOBOT
changes trading behavior.

## Files

- `AUTOBOT_RESEARCH_PROTOCOL.md`: how a trading idea moves from source review
  to backtest, shadow, official paper, and later human live review.
- `strategy_hypotheses.json`: machine-readable registry of current strategy
  hypotheses, evidence status, gates, and known risks.

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
