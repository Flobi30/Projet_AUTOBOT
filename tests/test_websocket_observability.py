import pytest

from autobot.v2.websocket_async import KrakenWebSocketAsync


pytestmark = pytest.mark.unit


def test_high_message_rate_log_is_rate_limited_and_not_a_drop(monkeypatch):
    monkeypatch.setenv("WS_HIGH_MESSAGE_RATE_LOG_INTERVAL_S", "60")
    websocket = KrakenWebSocketAsync()

    assert websocket._should_log_high_message_rate(now=100.0) is True
    assert websocket._should_log_high_message_rate(now=120.0) is False
    assert websocket._should_log_high_message_rate(now=161.0) is True

    websocket._last_msg_rate = 500.0
    websocket._backpressure_active = True
    health = websocket.get_health_snapshot()
    assert health["high_message_rate_active"] is True
    assert health["messages_per_second"] == 500.0
    assert health["explicit_drop_count"] == 0
    assert health["invalid_book_count"] is None
    assert health["book_metric_scope"] == "reported_by_order_flow_and_orchestrator_recovery"
