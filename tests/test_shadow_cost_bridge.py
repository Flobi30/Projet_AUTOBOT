import pytest

from autobot.v2.mean_reversion_shadow_lab import MeanReversionShadowConfig
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.setup_shadow_lab import SetupShadowLabConfig
from autobot.v2.shadow_cost_bridge import conservative_shadow_cost_defaults
from autobot.v2.shadow_paper_adapter import ShadowPaperExecutionAdapter
from autobot.v2.trend_shadow_lab import TrendShadowLabConfig


pytestmark = pytest.mark.unit


def test_shadow_cost_defaults_match_research_effective_fill_cost():
    defaults = conservative_shadow_cost_defaults(
        ExecutionCostConfig(
            taker_fee_bps=16.0,
            fallback_spread_bps=8.0,
            slippage_bps=4.0,
            latency_buffer_bps=1.0,
        )
    )

    assert defaults.fee_bps_per_side == pytest.approx(16.0)
    assert defaults.slippage_bps_per_side == pytest.approx(9.0)
    assert defaults.effective_cost_bps_per_side == pytest.approx(25.0)
    assert defaults.source == "research_execution_cost_model_legacy_shadow_bridge"


def test_shadow_lab_env_defaults_use_research_cost_bridge(monkeypatch):
    for name in (
        "TREND_SHADOW_FEE_BPS_PER_SIDE",
        "TREND_SHADOW_SLIPPAGE_BPS_PER_SIDE",
        "MEAN_REVERSION_SHADOW_FEE_BPS_PER_SIDE",
        "MEAN_REVERSION_SHADOW_SLIPPAGE_BPS_PER_SIDE",
        "SETUP_SHADOW_FEE_BPS_PER_SIDE",
        "SETUP_SHADOW_SLIPPAGE_BPS_PER_SIDE",
    ):
        monkeypatch.delenv(name, raising=False)

    trend = TrendShadowLabConfig.from_env()
    mean_reversion = MeanReversionShadowConfig.from_env()
    setup = SetupShadowLabConfig.from_env()
    defaults = conservative_shadow_cost_defaults()

    for config in (trend, mean_reversion, setup):
        assert config.fee_bps_per_side == pytest.approx(defaults.fee_bps_per_side)
        assert config.slippage_bps_per_side == pytest.approx(defaults.slippage_bps_per_side)
        assert config.to_dict()["effective_cost_bps_per_side"] == pytest.approx(defaults.effective_cost_bps_per_side)
        assert config.to_dict()["cost_model_source"] == "research_execution_cost_model_legacy_shadow_bridge"


def test_shadow_lab_env_overrides_remain_supported(monkeypatch):
    monkeypatch.setenv("TREND_SHADOW_FEE_BPS_PER_SIDE", "7")
    monkeypatch.setenv("TREND_SHADOW_SLIPPAGE_BPS_PER_SIDE", "2")

    config = TrendShadowLabConfig.from_env()

    assert config.fee_bps_per_side == pytest.approx(7.0)
    assert config.slippage_bps_per_side == pytest.approx(2.0)
    assert config.to_dict()["effective_cost_bps_per_side"] == pytest.approx(9.0)


def test_shadow_paper_adapter_metadata_uses_research_cost_bridge():
    metadata = ShadowPaperExecutionAdapter()._entry_metadata(
        engine="trend_momentum",
        best={"variant": "pytest_variant"},
        last_signal={"features": {"momentum_bps": 80.0, "atr_bps": 20.0}},
        last_decision={"reason": "candidate"},
    )

    defaults = conservative_shadow_cost_defaults()
    assert metadata["fee_bps"] == pytest.approx(defaults.fee_bps_per_side)
    assert metadata["exit_fee_bps"] == pytest.approx(defaults.fee_bps_per_side)
    assert metadata["slippage_bps"] == pytest.approx(defaults.slippage_bps_per_side)
    assert metadata["effective_cost_bps_per_side"] == pytest.approx(defaults.effective_cost_bps_per_side)
    assert metadata["cost_model_source"] == "research_execution_cost_model_legacy_shadow_bridge"
