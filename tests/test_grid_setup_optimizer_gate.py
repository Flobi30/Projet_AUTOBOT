from types import SimpleNamespace

import pytest

from autobot.v2.strategies.grid_async import GridStrategyAsync


pytestmark = pytest.mark.unit


class _Variant:
    def __init__(self, name="grid_defensive_observe", score=31.0):
        self.name = name
        self.score = score

    def to_dict(self):
        return {"name": self.name, "score": self.score}


class _Optimizer:
    def __init__(self, status, action):
        self.config = SimpleNamespace(enabled=True, apply_to_execution=True)
        self.status = status
        self.action = action

    def analyze_symbol(self, **_kwargs):
        return SimpleNamespace(
            status=self.status,
            recommended_action=self.action,
            selected_variant=_Variant(),
        )


class _Health:
    def build_snapshot_from_state_db(self, *_args, **_kwargs):
        return {
            "by_symbol": {
                "TRXEUR": {
                    "status": "underperforming",
                    "closed_trades": 42,
                    "net_pnl_eur": -4.2,
                    "profit_factor": 0.36,
                }
            }
        }


class _Shadow:
    def evidence_by_symbol(self):
        return {"TRXEUR": {"variants": []}}


def _strategy(status="pause_current", action="pause_current_setup_and_test_selected_variant_in_paper", paper=True):
    strategy = GridStrategyAsync.__new__(GridStrategyAsync)
    strategy.instance = SimpleNamespace(
        config=SimpleNamespace(symbol="TRXEUR"),
        orchestrator=SimpleNamespace(
            paper_mode=paper,
            setup_optimizer=_Optimizer(status, action),
            pair_strategy_health_engine=_Health(),
            setup_shadow_lab=_Shadow(),
            persistence=SimpleNamespace(db_path="unused.db"),
        ),
    )
    strategy.range_percent = 2.0
    strategy.num_levels = 15
    strategy.max_capital_per_level = 50.0
    strategy._setup_optimizer_execution_gate = True
    strategy._setup_optimizer_gate_ttl_s = 60.0
    strategy._setup_optimizer_gate_cache = (0.0, False, "cold_start", {})
    return strategy


def test_setup_optimizer_gate_blocks_bad_paper_setup():
    strategy = _strategy()

    blocked, reason, details = strategy._setup_optimizer_blocks_entry()

    assert blocked is True
    assert reason == "pause_current:pause_current_setup_and_test_selected_variant_in_paper"
    assert details["selected_variant"] == "grid_defensive_observe"
    assert details["health_status"] == "underperforming"


def test_setup_optimizer_gate_does_not_apply_outside_paper():
    strategy = _strategy(paper=False)

    blocked, reason, details = strategy._setup_optimizer_blocks_entry()

    assert blocked is False
    assert reason == "not_paper"
    assert details == {}
