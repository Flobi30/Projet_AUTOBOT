# PAPER_TRADING_OPERATIONS — ARCHIVED / NON-OPERATIONAL

This document is deliberately not an operating procedure.

AUTOBOT is currently restricted to research and non-executable shadow work.
Paper capital, strategy promotion, live trading, leverage changes and order
submission remain out of scope. No command, environment-variable matrix or
credential instruction in a historical paper guide may be used to alter that
state.

## Current operational reference

Use [the research/shadow incident runbook](runbooks/RESEARCH_SHADOW_INCIDENTS.md).
It documents only fail-closed, non-authorizing diagnostics and recovery
evidence.

## Future paper boundary

Paper can be considered only after all of the following:

1. A strategy independently passes the research, out-of-sample, cost and
   capacity gates.
2. The versioned layer coverage matrix has every required layer `VERIFIED`.
3. Kill-switch, reconciliation and restore drills are proven.
4. Fresh deployment evidence shows the same commit on GitHub, VPS and
   container, with healthy health/WebSocket checks, the code-level programme
   execution lock confirmed inside the container, and paper/live/promotion
   paths still disabled.
5. A `READY_FOR_HUMAN_PAPER_REVIEW` dossier is generated.
6. A human explicitly approves one bounded paper mandate.

The dossier itself never enables paper capital, live trading or promotion.

Historical instructions were removed from this working document to prevent
their accidental reuse. They remain recoverable through Git history if an
auditor needs provenance.
