from autobot.order_manager import Order, OrderSide
from autobot.position_manager import PositionManager, PositionStatus


class _DummyGridCalculator:
    def get_sell_levels(self):
        return [101.0, 102.0]


class _DummyOrderManager:
    def __init__(self):
        self._buy_order = None
        self._sell_order = None
        self.canceled = []

    def get_order_status(self, order_id, force_refresh=False):
        if self._buy_order and order_id == self._buy_order.id:
            return self._buy_order
        if self._sell_order and order_id == self._sell_order.id:
            return self._sell_order
        return None

    def place_sell_order(self, symbol, price, volume):
        return self._sell_order

    def cancel_order(self, order_id):
        self.canceled.append(order_id)
        return True


def test_open_position_rejects_missing_buy_order_id():
    manager = PositionManager(_DummyOrderManager(), _DummyGridCalculator())
    buy_order = Order(
        id=None,
        symbol="XXBTZEUR",
        side=OrderSide.BUY,
        price=100.0,
        volume=0.01,
    )

    try:
        manager.open_position(buy_order)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "buy_order.id manquant" in str(exc)


def test_open_position_tracks_with_non_null_buy_order_id():
    manager = PositionManager(_DummyOrderManager(), _DummyGridCalculator())
    buy_order = Order(
        id="buy_1",
        symbol="XXBTZEUR",
        side=OrderSide.BUY,
        price=100.0,
        volume=0.01,
    )

    position = manager.open_position(buy_order)

    assert position is not None
    assert position.buy_order_id == "buy_1"
    assert "buy_1" in manager._positions


def test_check_and_fill_position_does_not_index_none_sell_id():
    order_manager = _DummyOrderManager()
    manager = PositionManager(order_manager, _DummyGridCalculator())

    buy_order = Order(
        id="buy_2",
        symbol="XXBTZEUR",
        side=OrderSide.BUY,
        price=100.0,
        volume=0.01,
        status="closed",
        filled_volume=0.01,
    )
    order_manager._buy_order = buy_order
    order_manager._sell_order = Order(
        id=None,
        symbol="XXBTZEUR",
        side=OrderSide.SELL,
        price=101.0,
        volume=0.01,
        status="open",
    )

    opened = manager.open_position(buy_order)
    assert opened is not None

    filled = manager.check_and_fill_position("buy_2")

    assert filled is None
    assert manager._positions_by_sell == {}
    assert manager._positions["buy_2"].status != PositionStatus.FILLED
