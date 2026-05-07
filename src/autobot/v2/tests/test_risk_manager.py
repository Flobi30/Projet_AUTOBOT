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


class _FakeInstance:
    def __init__(self, profit: float, wins: int = 0, losses: int = 0):
        self._profit = profit
        self._win_count = wins
        self._loss_count = losses

    def get_profit(self):
        return self._profit


class _FakeOrchestrator:
    def __init__(self, paper_mode: bool):
        self.paper_mode = paper_mode
        self.emergency_stop_calls = 0

    async def emergency_stop_all(self):
        self.emergency_stop_calls += 1


@pytest.mark.asyncio
async def test_low_pf_does_not_stop_paper_by_default(monkeypatch):
    monkeypatch.delenv("RISK_MANAGER_PAPER_PF_STOP_ENABLED", raising=False)
    orchestrator = _FakeOrchestrator(paper_mode=True)
    manager = RiskManager(orchestrator=orchestrator)

    ok = await manager.check_global_risk(
        [_FakeInstance(1.0, wins=5), _FakeInstance(-10.0, losses=5)],
        paper_mode=True,
    )

    assert ok is True
    assert orchestrator.emergency_stop_calls == 0


@pytest.mark.asyncio
async def test_low_pf_still_stops_live(monkeypatch):
    monkeypatch.delenv("RISK_MANAGER_PAPER_PF_STOP_ENABLED", raising=False)
    orchestrator = _FakeOrchestrator(paper_mode=False)
    manager = RiskManager(orchestrator=orchestrator)

    ok = await manager.check_global_risk(
        [_FakeInstance(1.0, wins=1), _FakeInstance(-10.0, losses=1)],
        paper_mode=False,
    )

    assert ok is False
    assert orchestrator.emergency_stop_calls == 1


@pytest.mark.asyncio
async def test_paper_pf_stop_waits_for_minimum_closed_trade_evidence(monkeypatch):
    monkeypatch.setenv("RISK_MANAGER_PAPER_PF_STOP_ENABLED", "true")
    monkeypatch.setenv("RISK_MANAGER_PAPER_MIN_CLOSED_TRADES_FOR_PF_STOP", "30")
    orchestrator = _FakeOrchestrator(paper_mode=True)
    manager = RiskManager(orchestrator=orchestrator)

    ok = await manager.check_global_risk(
        [_FakeInstance(1.0, wins=5), _FakeInstance(-10.0, losses=5)],
        paper_mode=True,
    )

    assert ok is True
    assert orchestrator.emergency_stop_calls == 0


@pytest.mark.asyncio
async def test_paper_pf_stop_can_be_enabled_after_enough_evidence(monkeypatch):
    monkeypatch.setenv("RISK_MANAGER_PAPER_PF_STOP_ENABLED", "true")
    monkeypatch.setenv("RISK_MANAGER_PAPER_MIN_CLOSED_TRADES_FOR_PF_STOP", "30")
    orchestrator = _FakeOrchestrator(paper_mode=True)
    manager = RiskManager(orchestrator=orchestrator)

    ok = await manager.check_global_risk(
        [_FakeInstance(1.0, wins=20), _FakeInstance(-10.0, losses=20)],
        paper_mode=True,
    )

    assert ok is False
    assert orchestrator.emergency_stop_calls == 1
