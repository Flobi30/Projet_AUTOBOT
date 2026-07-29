# AUTOBOT Block 0.1 — Legacy Order Manager Execution Retirement

## Finding

The historical `autobot.order_manager.OrderManager` is outside AUTOBOT's
supported async runtime, but a caller could construct it with `sandbox=False`.
That mode contained direct private Kraken order and balance operations.

## Change

Non-sandbox construction now fails closed with
`LegacySynchronousRuntimeRetired` before any client initialization or private
API access. The default sandbox mode is retained only for existing hermetic
model and position tests; it is not a supported paper-capital route.

## Scope

No runtime order path, paper-capital path, live flag, promotion, sizing,
leverage, VPS service or data store changed. This is a local source-boundary
hardening increment only.

## Deployment

Hetzner maintenance is active. The increment is validated locally and may be
pushed to GitHub, but no VPS deployment or runtime operation is attempted.
