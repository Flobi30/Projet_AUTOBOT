"""
Compatibility entrypoint for AUTOBOT v2.

This module intentionally delegates to the async safe startup path
(`main_async.py`) to avoid operator confusion between legacy/sync and
current production startup flows.
"""

from __future__ import annotations

import logging

from autobot.v2.main_async import main as async_main

logger = logging.getLogger(__name__)


def main() -> None:
    """Delegate to the official async entrypoint."""
    logger.warning(
        "main.py is a compatibility wrapper; delegating to main_async.py"
    )
    async_main()


if __name__ == "__main__":
    main()
