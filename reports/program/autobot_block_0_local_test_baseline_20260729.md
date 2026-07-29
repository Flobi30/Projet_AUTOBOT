# AUTOBOT Block 0 — Local Test Baseline — 2026-07-29

## Scope

This is a local, non-deployment verification recorded while the Hetzner VPS is
unavailable.  It does not start a runtime, collector, shadow run, paper
engine, live path, Docker service, or network client.

## Evidence

Executed from the repository root with `PYTHONPATH=src`:

```text
python -m pytest --collect-only -q
```

Result:

```text
2048/2050 tests collected (2 deselected)
```

The collection completed without an import-time error or a missing test
dependency.

Executed immediately afterwards:

```text
python -m pytest -q
```

Result:

```text
2042 passed, 6 skipped, 2 deselected in 61.12s
```

## Decision

`GO_LOCAL` — local implementation and verification may continue.  This is not
a VPS deployment approval and does not replace the required rebuild, smoke
check, commit alignment, or runtime safety verification after the VPS returns.

## Safety

- No production endpoint, private Kraken endpoint, SSH command, Docker command
  or order path was called.
- The programme remains research/shadow-only; paper capital, promotion and
  live trading are outside this verification.
