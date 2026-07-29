"""Retired legacy private Kraken API test entry point.

This module intentionally contains no credential handling, private client, or
network request. Historical implementation is available through Git history;
the supported AUTOBOT test surface is hermetic and research/shadow-only.
"""

from __future__ import annotations

import pytest

from autobot.v2.legacy_runtime import reject_legacy_synchronous_runtime


pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.external,
]


class KrakenAPITester:
    """Compatibility shell for an archived manual private-API tool."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        reject_legacy_synchronous_runtime("legacy Kraken private API test harness")


def main() -> None:
    """Fail closed instead of running the archived private Kraken test CLI."""

    reject_legacy_synchronous_runtime("legacy Kraken private API test CLI")


if __name__ == "__main__":
    main()
