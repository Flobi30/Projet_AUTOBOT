# AUTOBOT Block 0.1 — Legacy Operator Tool Retirement

## Finding

Three historical operator tools still documented or automated flows outside
the research/shadow programme: a preflight script that displayed key material
and constructed archived Grid components, a paper operations guide that
recommended paper activation, and a VPS setup script that requested private
credentials and wrote an environment file in clear text.

## Change

The preflight and VPS setup entry points are now small
`retired_from_execution` stubs. They exit before reading environment variables,
importing runtime code, requesting credentials, writing an environment file,
starting Docker, or performing a network action.

The retained `paper_ops.py` name now exposes only read-only log summarization
and a preflight-only attestation artifact. Its former validation command
refuses the retired activation workflow before reading the supplied environment
file; launch and feature-flag guidance no longer exist. Historical content
remains recoverable through Git history.

## Safety Result

No paper activation, live activation, promotion, sizing, leverage, order
submission, VPS action or secret operation is introduced. The supported paths
remain the hermetic test suite, public research collectors and controlled
observation-only deployment scripts.

## Deployment

Hetzner maintenance is active. This local hardening is not deployed or run on
the VPS until controlled validation can resume.
