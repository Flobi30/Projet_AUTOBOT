#!/usr/bin/env python3
"""Retired legacy preflight entry point.

This historical script previously encouraged private credentials, paper
activation and archived Grid runtime construction. It is not part of the
research/shadow programme and intentionally performs no environment read,
import of a runtime component, or network operation.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("AUTOBOT legacy preflight is retired_from_execution.")
    print("Use the hermetic test suite and observation-only readiness audits instead.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
