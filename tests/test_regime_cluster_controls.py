import pytest

from autobot.v2.regime_controller import RegimeController
from autobot.v2.risk_cluster_manager import RiskClusterManager


pytestmark = pytest.mark.integration

class _Cfg:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _Inst:
    def __init__(self, symbol: str, cap: float):
        self.config = _Cfg(symbol)
        self._cap = cap

    def get_current_capital(self):
        return self._cap


def test_regime_controller_hysteresis_and_policy():
    rc = RegimeController(hysteresis_ticks=2)
    s1 = rc.update("BTC/USD", trend="up", volatility=0.02, drawdown=0.01)
    s2 = rc.update("BTC/USD", trend="up", volatility=0.02, drawdown=0.01)
    assert s2.regime in ("TREND", "RANGE")
    policy = rc.module_policy(s2.regime)
    assert "enable_ml" in policy


def test_cluster_risk_cap_reduces_multiplier_when_overexposed():
    rcm = RiskClusterManager(cluster_cap=0.30)
    instances = [_Inst("BTC/USD", 7000.0), _Inst("ETH/USD", 2000.0), _Inst("SOL/USD", 1000.0)]
    exp = rcm.exposure_by_cluster(instances)
    mult = rcm.allowed_multiplier("BTC/USD", add_size=1000.0, total_capital=10000.0, exposures=exp)
    assert 0.1 <= mult < 1.0
