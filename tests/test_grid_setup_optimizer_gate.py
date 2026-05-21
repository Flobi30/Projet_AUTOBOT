from types import SimpleNamespace

import pytest

from autobot.v2.strategies.grid_async import GridStrategyAsync


pytestmark = pytest.mark.unit


class _Variant:
    def __init__(self, name="grid_defensive_observe", score=31.0, grid_config=None):
        self.name = name
        self.score = score
        self.grid_config = grid_config

    def to_dict(self):
        payload = {"name": self.name, "score": self.score}
        if self.grid_config is not None:
            payload["grid_config"] = dict(self.grid_config)
        return payload


class _Optimizer:
    def __init__(self, status, action, variant=None):
        self.config = SimpleNamespace(enabled=True, apply_to_execution=True)
        self.status = status
        self.action = action
        self.variant = variant or _Variant()

    def analyze_symbol(self, **_kwargs):
        return SimpleNamespace(
            status=self.status,
            recommended_action=self.action,
            selected_variant=self.variant,
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


def _strategy(status="pause_current", action="pause_current_setup_and_test_selected_variant_in_paper", paper=True, variant=None):
    strategy = GridStrategyAsync.__new__(GridStrategyAsync)
    instance = SimpleNamespace(config=SimpleNamespace(symbol="TRXEUR"))
    instance.get_available_capital = lambda: 100.0
    instance.orchestrator = SimpleNamespace(
        paper_mode=paper,
        setup_optimizer=_Optimizer(status, action, variant=variant),
        pair_strategy_health_engine=_Health(),
        setup_shadow_lab=_Shadow(),
        persistence=SimpleNamespace(db_path="unused.db"),
    )
    strategy.instance = SimpleNamespace(
        config=SimpleNamespace(symbol="TRXEUR"),
        orchestrator=instance.orchestrator,
    )
    strategy.instance.get_available_capital = lambda: 100.0
    strategy.range_percent = 2.0
    strategy.num_levels = 15
    strategy.max_capital_per_level = 50.0
    strategy.max_positions = 10
    strategy.center_price = 100.0
    strategy.grid_levels = []
    strategy.open_levels = {}
    strategy.trailing_stops = {}
    strategy._dgt = None
    strategy._spec_cache = None
    strategy._adaptive_mode = False
    strategy._grid_allocator = None
    strategy._pair_profile = None
    strategy._grid_initialized = True
    strategy._emergency_mode = False
    strategy._grid_invalidation_factor = 2.0
    strategy._entry_touch_bps = 15.0
    strategy._sell_threshold_pct = 1.5
    strategy._setup_optimizer_execution_gate = True
    strategy._setup_optimizer_gate_ttl_s = 60.0
    strategy._setup_optimizer_gate_cache = (0.0, False, "cold_start", {})
    strategy._paper_execution_router_enabled = True
    strategy._paper_execution_block_pending = True
    strategy._paper_execution_min_score = 70.0
    strategy._paper_execution_profile = {
        "enabled": True,
        "mode": "paper_only",
        "active_variant": "grid_registry_default",
        "status": "startup",
        "last_reason": "not_evaluated",
        "last_action_at": None,
        "pending_variant": None,
        "applied_count": 0,
    }
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


def test_setup_optimizer_candidate_applies_grid_config_when_flat():
    variant = _Variant(
        name="grid_tight_range",
        score=82.0,
        grid_config={
            "range_percent": 1.5,
            "num_levels": 19,
            "max_capital_per_level": 12.0,
            "max_positions": 6,
            "entry_touch_bps": 8.0,
        },
    )
    strategy = _strategy(
        status="candidate",
        action="paper_shadow_candidate_review",
        variant=variant,
    )

    blocked, _reason, details = strategy._setup_optimizer_blocks_entry(current_price=101.0)

    assert blocked is False
    assert details["paper_execution"]["action"] == "applied"
    assert strategy.range_percent == 1.5
    assert strategy.num_levels == 19
    assert strategy.max_capital_per_level == 12.0
    assert strategy.max_positions == 6
    assert strategy._entry_touch_bps == 8.0
    assert strategy._paper_execution_profile["active_variant"] == "grid_tight_range"


def test_setup_optimizer_candidate_defers_until_flat_and_blocks_new_buys():
    variant = _Variant(
        name="grid_wide",
        score=88.0,
        grid_config={
            "range_percent": 4.0,
            "num_levels": 11,
            "max_capital_per_level": 20.0,
            "max_positions": 4,
            "entry_touch_bps": 10.0,
        },
    )
    strategy = _strategy(
        status="candidate",
        action="paper_shadow_candidate_review",
        variant=variant,
    )
    strategy.open_levels = {3: {"entry_price": 100.0, "volume": 1.0}}

    blocked, _reason, details = strategy._setup_optimizer_blocks_entry(current_price=101.0)

    assert blocked is True
    assert details["paper_execution"]["action"] == "defer_until_flat"
    assert details["paper_execution"]["block_new_entries"] is True
    assert strategy.range_percent == 2.0
    assert strategy._paper_execution_profile["pending_variant"] == "grid_wide"
