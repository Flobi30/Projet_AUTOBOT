from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot.v2.orchestrator_async import OrchestratorAsync


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_order_book_recovery_resets_and_resubscribes_invalid_books():
    orchestrator = OrchestratorAsync.__new__(OrchestratorAsync)
    orchestrator._order_book_recovery_enabled = True
    orchestrator._order_book_recovery_interval_s = 20.0
    orchestrator._order_book_recovery_cooldown_s = 30.0
    orchestrator._order_book_recovery_min_invalid_count = 1
    orchestrator._order_book_recovery_max_per_cycle = 4
    orchestrator._order_book_recovery_last_attempt = {}
    orchestrator._order_book_recovery_stats = {
        "enabled": True,
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "last_actions": [],
    }
    orchestrator.running = True
    orchestrator.ws_client = SimpleNamespace(is_connected=lambda: True)
    orchestrator.ring_dispatcher = SimpleNamespace(resubscribe_book=AsyncMock())
    orchestrator._instances = {
        "inst-1": SimpleNamespace(config=SimpleNamespace(symbol="XXBTZEUR")),
        "inst-2": SimpleNamespace(config=SimpleNamespace(symbol="TRXEUR")),
    }

    class _Ofi:
        def __init__(self):
            self.reset_symbols = []

        def get_quality_snapshot(self, symbol):
            if symbol == "XXBTZEUR":
                return {"reason": "invalid_book", "invalid_count": 2}
            return {"reason": "ok", "invalid_count": 0}

        def reset_book(self, symbol, reason):
            self.reset_symbols.append((symbol, reason))
            return {"reset": True, "reset_count": 1}

    orchestrator.ofi = _Ofi()

    result = await OrchestratorAsync._recover_invalid_order_books(orchestrator)

    assert result["attempts"] == 1
    assert result["successes"] == 1
    assert result["last_status"] == "actions_taken"
    assert orchestrator.ofi.reset_symbols == [("XXBTZEUR", "invalid_book_resubscribe")]
    orchestrator.ring_dispatcher.resubscribe_book.assert_awaited_once_with("XXBTZEUR")


@pytest.mark.asyncio
async def test_order_book_recovery_respects_cooldown():
    orchestrator = OrchestratorAsync.__new__(OrchestratorAsync)
    orchestrator._order_book_recovery_enabled = True
    orchestrator._order_book_recovery_interval_s = 20.0
    orchestrator._order_book_recovery_cooldown_s = 30.0
    orchestrator._order_book_recovery_min_invalid_count = 1
    orchestrator._order_book_recovery_max_per_cycle = 4
    orchestrator._order_book_recovery_last_attempt = {"XXBTZEUR": 10**9}
    orchestrator._order_book_recovery_stats = {
        "enabled": True,
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "last_actions": [],
    }
    orchestrator.running = True
    orchestrator.ws_client = SimpleNamespace(is_connected=lambda: True)
    orchestrator.ring_dispatcher = SimpleNamespace(resubscribe_book=AsyncMock())
    orchestrator._instances = {"inst-1": SimpleNamespace(config=SimpleNamespace(symbol="XXBTZEUR"))}
    orchestrator.ofi = SimpleNamespace(
        get_quality_snapshot=lambda _symbol: {"reason": "invalid_book", "invalid_count": 2},
        reset_book=lambda *_args, **_kwargs: {"reset": True},
    )

    result = await OrchestratorAsync._recover_invalid_order_books(orchestrator)

    assert result["attempts"] == 0
    assert result["last_status"] == "no_invalid_books_ready"
    orchestrator.ring_dispatcher.resubscribe_book.assert_not_awaited()
