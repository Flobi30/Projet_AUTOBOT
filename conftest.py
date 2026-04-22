from __future__ import annotations

import pytest

_REQUIRED_MARKERS = {"unit", "integration", "e2e"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Fail collection when a test has no explicit suite marker.

    A test must be tagged (module/class/function) with at least one of:
    - unit
    - integration
    - e2e
    """

    unmarked: list[str] = []
    for item in items:
        item_markers = {mark.name for mark in item.iter_markers()}
        if item_markers.isdisjoint(_REQUIRED_MARKERS):
            location = f"{item.location[0]}:{item.location[1] + 1}"
            unmarked.append(location)

    if unmarked:
        details = "\n".join(f"- {location}" for location in sorted(unmarked))
        raise pytest.UsageError(
            "Every test must declare at least one suite marker "
            "(unit/integration/e2e). Missing markers:\n"
            f"{details}"
        )
