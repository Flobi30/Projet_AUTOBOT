from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.shadow_paper_adapter import ShadowPaperAdapterConfig, ShadowPaperExecutionAdapter


pytestmark = pytest.mark.unit


def test_shadow_paper_adapter_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PAPER_EXECUTION_ADAPTER_ENABLED", raising=False)

    assert ShadowPaperAdapterConfig.from_env().enabled is False


@pytest.mark.asyncio
async def test_disabled_adapter_never_calls_the_signal_handler():
    adapter = ShadowPaperExecutionAdapter()
    handler = SimpleNamespace(calls=0)
    instance = SimpleNamespace(_signal_handler=handler)

    result = await adapter.mirror_if_needed(
        instance=instance,
        governance_row={"execution_mode": "shadow_signal_mirror"},
        shadow_symbol_row={},
    )

    assert result == {"handled": False, "reason": "adapter_disabled"}
    assert handler.calls == 0


@pytest.mark.asyncio
async def test_enabled_adapter_does_not_claim_a_blocked_entry_was_handled():
    adapter = ShadowPaperExecutionAdapter(ShadowPaperAdapterConfig(enabled=True))

    class _Handler:
        _last_decision_event = {
            "reason": "legacy_direct_execution_disabled",
            "shadow_contract_preview": {"status": "SHADOW_PREVIEW_REJECTED"},
        }

        async def _on_signal(self, _signal):
            return None

    instance = SimpleNamespace(
        _signal_handler=_Handler(),
        get_positions_snapshot=lambda: [],
    )
    result = await adapter.mirror_if_needed(
        instance=instance,
        governance_row={
            "execution_mode": "shadow_signal_mirror",
            "selected_engine": "trend_momentum",
            "symbol": "BTCEUR",
        },
        shadow_symbol_row={
            "symbol": "BTCEUR",
            "best_variant": {
                "variant": "trend-v1",
                "last_price": 65_000.0,
                "last_signal": {"price": 65_000.0, "features": {"momentum_bps": 50.0}},
                    "last_decision": {
                        "status": "opened",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "notional_eur": 20.0,
                    "reason": "test",
                },
            },
        },
    )

    assert result["handled"] is False
    assert result["reason"] == "legacy_direct_execution_disabled"
    assert result["shadow_contract_preview"]["status"] == "SHADOW_PREVIEW_REJECTED"
