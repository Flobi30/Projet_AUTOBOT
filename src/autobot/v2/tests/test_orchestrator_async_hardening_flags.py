import pytest

from autobot.v2.orchestrator_async import _apply_force_enable_all_hardening_flags


pytestmark = pytest.mark.unit


def _base_hardening_flags() -> dict[str, bool]:
    return {
        "enable_mean_reversion": False,
        "enable_sentiment": False,
        "enable_ml": False,
        "enable_xgboost": False,
        "enable_onchain": False,
        "enable_trading_health_score": False,
        "enable_shadow_promotion": False,
        "enable_shadow_trading": False,
        "enable_rebalance": False,
        "enable_auto_evolution": False,
        "enable_validation_guard": False,
    }


def test_force_enable_all_unset_keeps_safe_default_without_override(monkeypatch):
    monkeypatch.delenv("AUTOBOT_FORCE_ENABLE_ALL", raising=False)
    hardening_flags = _base_hardening_flags()

    _apply_force_enable_all_hardening_flags(hardening_flags)

    assert all(value is False for value in hardening_flags.values())


def test_force_enable_all_true_applies_override(monkeypatch):
    monkeypatch.setenv("AUTOBOT_FORCE_ENABLE_ALL", "true")
    hardening_flags = _base_hardening_flags()

    _apply_force_enable_all_hardening_flags(hardening_flags)

    assert all(value is True for value in hardening_flags.values())
