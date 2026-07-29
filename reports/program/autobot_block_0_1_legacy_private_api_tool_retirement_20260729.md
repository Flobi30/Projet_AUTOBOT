# AUTOBOT Block 0.1 — Legacy Private Kraken API Tool Retirement

## Finding

The archived `src/autobot/v2/tests/test_kraken_api.py` utility and its shell
wrapper could still read Kraken credentials, query private balances and order
state, submit an `AddOrder` validation request, and cancel open orders if a
developer launched them manually. They were outside the supported async
runtime, but their existence conflicted with the research/shadow-only safety
boundary.

## Change

- The Python harness now raises `LegacySynchronousRuntimeRetired` before it
  reads credentials, constructs `krakenex.API`, or calls a network endpoint.
- Its CLI entry point is equally retired before argument or environment
  handling.
- The shell wrapper is a non-interactive retired notice; it neither reads nor
  forwards API credentials.
- The legacy test README now directs contributors to public-data collectors
  and hermetic tests only.

## Safety Result

The current programme retains no supported command that can invoke this
legacy private Kraken test route. This change does not activate paper capital,
live trading, promotion, order routing, sizing, leverage, or the VPS runtime.

## Validation

Focused retirement tests prove the Python and shell entry points fail closed
before private client construction or credential forwarding. The full suite is
run before the associated commit.

## Deployment

Hetzner maintenance is active. No VPS access, build, restart, deployment or
runtime data operation is attempted for this local safety hardening.
