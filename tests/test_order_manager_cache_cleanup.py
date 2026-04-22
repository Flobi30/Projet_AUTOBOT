import pytest

from datetime import timedelta, timezone, datetime

from autobot.order_manager import Order, OrderManager


pytestmark = pytest.mark.integration

def _make_closed_order(order_id: str, closed_at: datetime) -> Order:
    return Order(id=order_id, status="closed", closed_at=closed_at)


def test_cleanup_closed_orders_keeps_recent_closed_order():
    manager = OrderManager(sandbox=True)
    now = datetime.now(timezone.utc)
    manager._active_orders["recent"] = _make_closed_order(
        "recent", closed_at=now - timedelta(hours=1)
    )

    removed = manager.cleanup_closed_orders(max_age_hours=24)

    assert removed == 0
    assert "recent" in manager._active_orders


def test_cleanup_closed_orders_removes_old_closed_order():
    manager = OrderManager(sandbox=True)
    now = datetime.now(timezone.utc)
    manager._active_orders["old"] = _make_closed_order(
        "old", closed_at=now - timedelta(hours=48)
    )

    removed = manager.cleanup_closed_orders(max_age_hours=24)

    assert removed == 1
    assert "old" not in manager._active_orders


def test_cleanup_closed_orders_default_max_age():
    manager = OrderManager(sandbox=True)
    now = datetime.now(timezone.utc)
    manager._active_orders["old"] = _make_closed_order(
        "old", closed_at=now - timedelta(hours=25)
    )
    manager._active_orders["recent"] = _make_closed_order(
        "recent", closed_at=now - timedelta(hours=2)
    )

    removed = manager.cleanup_closed_orders()

    assert removed == 1
    assert "old" not in manager._active_orders
    assert "recent" in manager._active_orders


def test_cleanup_closed_orders_immediate_when_non_positive_max_age():
    manager = OrderManager(sandbox=True)
    now = datetime.now(timezone.utc)
    manager._active_orders["recent"] = _make_closed_order(
        "recent", closed_at=now - timedelta(minutes=5)
    )

    removed = manager.cleanup_closed_orders(max_age_hours=0)

    assert removed == 1
    assert "recent" not in manager._active_orders
