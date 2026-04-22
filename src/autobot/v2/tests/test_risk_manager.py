import pytest

from autobot.v2.risk_manager import RiskConfig, RiskManager


pytestmark = pytest.mark.unit


def test_get_config_for_capital_uses_first_tier_for_capital_below_minimum():
    manager = RiskManager()

    config = manager.get_config_for_capital(50)

    assert config == manager.configs[0]


def test_get_config_for_capital_handles_tier_boundaries():
    manager = RiskManager()

    assert manager.get_config_for_capital(100) == manager.configs[0]
    assert manager.get_config_for_capital(500) == manager.configs[1]
    assert manager.get_config_for_capital(1000) == manager.configs[2]
    assert manager.get_config_for_capital(2000) == manager.configs[3]
    assert manager.get_config_for_capital(5000) == manager.configs[4]


def test_get_config_for_capital_above_max_falls_back_to_last_tier():
    manager = RiskManager(
        configs=[
            RiskConfig(100, 200, -0.20, 0.30, 2, 1, "tier-1"),
            RiskConfig(200, 300, -0.15, 0.25, 3, 2, "tier-2"),
        ]
    )

    assert manager.get_config_for_capital(10_000) == manager.configs[-1]


@pytest.mark.parametrize(
    "configs",
    [
        # Non triés
        [
            RiskConfig(200, 300, -0.15, 0.25, 3, 2, "tier-2"),
            RiskConfig(100, 200, -0.20, 0.30, 2, 1, "tier-1"),
        ],
        # Trou entre paliers
        [
            RiskConfig(100, 200, -0.20, 0.30, 2, 1, "tier-1"),
            RiskConfig(250, 300, -0.15, 0.25, 3, 2, "tier-2"),
        ],
        # Chevauchement
        [
            RiskConfig(100, 250, -0.20, 0.30, 2, 1, "tier-1"),
            RiskConfig(200, 300, -0.15, 0.25, 3, 2, "tier-2"),
        ],
    ],
)
def test_risk_manager_validates_tier_consistency_at_startup(configs):
    with pytest.raises(ValueError):
        RiskManager(configs=configs)
