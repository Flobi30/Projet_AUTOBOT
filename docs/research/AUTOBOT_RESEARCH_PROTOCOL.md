# AUTOBOT Research Protocol

## Decision Question

Which data, strategy, validation, risk, and execution changes can make AUTOBOT
more robust in paper trading without making paper easier than future live
trading?

## Evidence Levels

| Level | Source Type | Use In AUTOBOT |
|---|---|---|
| A | Official API docs, regulation, rigorous systematic reviews | Hard constraints and definitions |
| B | Maintained framework docs, robust empirical papers, reproducible repos | Strong design guidance |
| C | Preprints, engineering blogs with code, forum patterns corroborated elsewhere | Hypotheses to test |
| D | Marketing, unverifiable screenshots, guaranteed-return claims | Exclude from decisions |

## Research Log Minimum

Every research-driven change should record:

- hypothesis id;
- problem being solved;
- source links and evidence level;
- market regime targeted;
- baseline comparator;
- expected failure mode;
- test plan;
- paper/live parity risks;
- decision: `learning`, `candidate`, `validated_paper`, `rejected`, or `deferred`.

## Strategy Lifecycle

1. **Research idea**
   - Define the market behavior the strategy claims to exploit.
   - Identify when it should not trade.
   - Document fees, spread, slippage, latency, and minimum order assumptions.

2. **Backtest or offline replay**
   - Compare to no-trade and simple baselines.
   - Use net PnL after costs, PF, drawdown, median trade, win/loss ratio, and
     sample size.
   - Reject if the edge disappears after realistic costs.

3. **Shadow lab**
   - Strategy may simulate decisions but must not write official paper trades.
   - Store every accepted/rejected decision with reason and timestamp.
   - Penalize tiny samples and no-loss samples.

4. **Official paper candidate**
   - Requires promotion gate pass:
     - enough closed shadow trades;
     - positive net PnL after costs;
     - PF above configured threshold;
     - acceptable drawdown;
     - no severe reconciliation divergence;
     - no live auto-promotion.

5. **Official paper execution**
   - Must use the same cost, risk, symbol, precision, and minimum order checks
     expected for future live.
   - Must write to the official ledger.

6. **Live review**
   - Human approval only.
   - Requires paper/live parity review, Kraken permissions review, kill-switch
     review, and small-capital staged rollout.

## Current AUTOBOT Diagnosis

AUTOBOT already has valuable sensors:

- opportunity scoring;
- cost/edge guard;
- microstructure filter;
- regime scoring;
- shadow labs for grid, trend, and mean reversion;
- strategy router;
- promotion gate;
- governance/reconciliation.

The weak point is not observability. The weak point is proving that one strategy
adds durable net edge after fees and execution friction. Recent paper history
shows negative aggregate PnL and only isolated pair-level strength. Therefore
the next research work should focus on evidence quality, not trade count.

## Change Approval Checklist

Before coding a strategy or changing parameters:

- Is this solving alpha quality, execution realism, risk control, or reporting?
- Is the source level A/B/C, and is the limitation documented?
- Does the change preserve paper-first behavior?
- Does it avoid live activation?
- Does it compare against no-trade and current official paper?
- Does it improve measured evidence instead of merely increasing trades?

## What Not To Do

- Do not lower thresholds only to force trades.
- Do not promote shadow PnL without official paper reconciliation.
- Do not treat a single positive pair as global strategy proof.
- Do not add ML/AI models before the data, label, and validation pipeline are
  trustworthy.
- Do not optimize on the same paper sample used to judge success.
