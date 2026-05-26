from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.market_data_quality import MarketDataQualityEngine


pytestmark = pytest.mark.unit


def test_market_data_quality_reports_healthy_symbol_with_book():
    class _Ofi:
        def get_quality_snapshot(self, _symbol):
            return {
                "has_book": True,
                "reason": "ok",
                "bid": 99.9,
                "ask": 100.1,
                "spread_bps": 20.0,
                "age_ms": 50.0,
            }

    orchestrator = SimpleNamespace(
        ofi=_Ofi(),
        ring_dispatcher=SimpleNamespace(
            get_health_snapshot=lambda: {"connected": True, "backpressure_active": False}
        ),
    )
    now = datetime.now(timezone.utc).isoformat()
    instances = [
        {
            "symbol": "XXBTZEUR",
            "last_price": 100.0,
            "last_tick": {"timestamp": now},
            "warmup": {"price_samples": 64},
        }
    ]

    snapshot = MarketDataQualityEngine(max_price_age_ms=30_000, max_book_age_ms=5_000).build_snapshot(
        orchestrator=orchestrator,
        instances=instances,
        paper_mode=True,
    )

    assert snapshot["summary"]["healthy_symbols"] == 1
    assert snapshot["symbols"][0]["status"] == "healthy"
    assert snapshot["symbols"][0]["recommended_action"] == "eligible_for_microstructure_checks"


def test_market_data_quality_blocks_when_required_book_is_missing():
    class _Ofi:
        def get_quality_snapshot(self, _symbol):
            return {"has_book": False, "reason": "book_unavailable"}

    orchestrator = SimpleNamespace(
        ofi=_Ofi(),
        ring_dispatcher=SimpleNamespace(
            get_health_snapshot=lambda: {"connected": True, "backpressure_active": True}
        ),
    )
    instances = [{"symbol": "TRXEUR", "last_price": 0.1, "warmup": {"price_samples": 32}}]

    snapshot = MarketDataQualityEngine(require_book_for_microstructure=True).build_snapshot(
        orchestrator=orchestrator,
        instances=instances,
        paper_mode=True,
    )

    row = snapshot["symbols"][0]
    assert snapshot["summary"]["blocked_symbols"] == 1
    assert "book_unavailable" in row["blockers"]
    assert "websocket_backpressure_active" in row["warnings"]
    assert snapshot["recommended_action"] == "order_book_feed_not_usable_for_any_symbol"


def test_market_data_quality_includes_recovery_diagnostics():
    class _Ofi:
        def get_quality_snapshot(self, _symbol):
            return {"has_book": False, "reason": "invalid_book", "invalid_count": 2, "reset_count": 1}

        def get_recovery_snapshot(self):
            return {"total_resets": 1, "symbols": {"TRXEUR": {"reset_count": 1}}}

    orchestrator = SimpleNamespace(
        ofi=_Ofi(),
        _order_book_recovery_stats={"enabled": True, "attempts": 1, "successes": 1},
        ring_dispatcher=SimpleNamespace(
            get_health_snapshot=lambda: {"connected": True, "backpressure_active": False}
        ),
    )
    instances = [{"symbol": "TRXEUR", "last_price": 0.1, "warmup": {"price_samples": 32}}]

    snapshot = MarketDataQualityEngine(require_book_for_microstructure=True).build_snapshot(
        orchestrator=orchestrator,
        instances=instances,
        paper_mode=True,
    )

    assert snapshot["recovery"]["runtime"]["attempts"] == 1
    assert snapshot["recovery"]["ofi"]["total_resets"] == 1
    assert snapshot["symbols"][0]["book"]["reset_count"] == 1
