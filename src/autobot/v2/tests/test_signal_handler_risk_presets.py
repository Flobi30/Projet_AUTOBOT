from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from autobot.v2.signal_handler_async import RISK_REGIME_PRESETS, SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal

pytestmark = pytest.mark.unit


def _make_handler(price_history=None, preset="balanced"):
    handler = SignalHandlerAsync.__new__(SignalHandlerAsync)
    handler.instance = SimpleNamespace(_price_history=price_history or [])
    handler._fallback_atr_pct = 0.012
    handler._risk_regime_preset = preset
    handler._base_atr_sl_mult = 1.8
    handler._base_tp_rr = 1.6
    handler._base_min_edge_bps = 12.0
    return handler


def _signal(regime: str, spread_bps: float = 0.0):
    return TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.1,
        reason="test",
        timestamp=datetime.now(timezone.utc),
        metadata={"regime": regime, "spread_bps": spread_bps},
    )


def test_presets_expose_range_and_trend_profiles():
    assert set(RISK_REGIME_PRESETS.keys()) >= {"balanced", "defensive", "offensive"}
    for preset in RISK_REGIME_PRESETS.values():
        assert set(preset.keys()) == {"RANGE", "TREND"}


def test_defensive_trend_has_higher_rr_than_balanced_in_same_context():
    handler_balanced = _make_handler(preset="balanced")
    handler_defensive = _make_handler(preset="defensive")

    signal = _signal("TREND", spread_bps=12.0)
    balanced = handler_balanced._resolve_dynamic_risk_params(signal, atr_pct=0.013)
    defensive = handler_defensive._resolve_dynamic_risk_params(signal, atr_pct=0.013)

    assert defensive["tp_rr"] > balanced["tp_rr"]
    assert defensive["min_edge_bps"] > balanced["min_edge_bps"]


def test_high_spread_enforces_higher_min_rr_floor():
    handler = _make_handler(preset="offensive")
    signal = _signal("RANGE", spread_bps=90.0)

    params = handler._resolve_dynamic_risk_params(signal, atr_pct=0.012)

    assert params["tp_rr"] >= 1.20 + (90.0 / 120.0)
