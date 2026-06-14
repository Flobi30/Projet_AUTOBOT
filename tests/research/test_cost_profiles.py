import pytest

from autobot.v2 import cli
from autobot.v2.cost_profiles import COST_PROFILE_NAMES, get_cost_profile
from autobot.v2.paper_trading import PaperTradingExecutor
from autobot.v2.research.execution_cost_model import (
    ExecutionCostModel,
    FillRequest,
    execution_cost_config_for_profile,
)


pytestmark = pytest.mark.unit


def test_canonical_cost_profiles_have_expected_round_trip_estimates():
    assert set(COST_PROFILE_NAMES) == {
        "paper_current_taker",
        "paper_current_maker",
        "research_stress",
        "research_legacy",
    }
    assert get_cost_profile("paper_current_taker").round_trip_cost_estimate_bps == pytest.approx(94.0)
    assert get_cost_profile("paper_current_maker").round_trip_cost_estimate_bps == pytest.approx(50.0)
    assert get_cost_profile("research_stress").round_trip_cost_estimate_bps == pytest.approx(98.0)
    assert get_cost_profile("research_legacy").round_trip_cost_estimate_bps == pytest.approx(50.0)


def test_legacy_profile_is_retained_but_not_runtime_comparable():
    config = execution_cost_config_for_profile("research_legacy")

    assert config.cost_profile == "research_legacy"
    assert config.legacy is True
    assert config.runtime_comparable is False
    assert config.to_dict()["round_trip_cost_estimate_bps"] == pytest.approx(50.0)


def test_stress_profile_cost_estimate_matches_two_simulated_market_legs():
    config = execution_cost_config_for_profile("research_stress")
    model = ExecutionCostModel(config)
    request = FillRequest(symbol="BCHEUR", side="buy", price=100.0, notional_eur=100.0)

    per_leg = model.estimate_cost_bps(request)

    assert per_leg == pytest.approx(49.0)
    assert 2.0 * per_leg == pytest.approx(config.round_trip_cost_estimate_bps())


def test_cli_cost_profile_supports_explicit_overrides():
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "backtest",
            "--run-id",
            "cost_profile_parse",
            "--strategy",
            "grid",
            "--data-source",
            "csv",
            "--data-path",
            "unused.csv",
            "--symbol",
            "BCHEUR",
            "--cost-profile",
            "paper_current_taker",
            "--spread-bps",
            "12",
        ]
    )
    config = cli._cost_config_from_args(args)

    assert config.cost_profile == "paper_current_taker"
    assert config.taker_fee_bps == pytest.approx(40.0)
    assert config.fallback_spread_bps == pytest.approx(12.0)
    assert config.round_trip_cost_estimate_bps() == pytest.approx(98.0)


def test_paper_executor_keeps_current_fee_behavior_and_exposes_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPER_MAKER_FEE_BPS", raising=False)
    monkeypatch.delenv("PAPER_TAKER_FEE_BPS", raising=False)
    executor = PaperTradingExecutor(db_path=str(tmp_path / "paper.db"))

    summary = executor.get_trade_summary()

    assert summary["maker_fee_bps"] == pytest.approx(25.0)
    assert summary["taker_fee_bps"] == pytest.approx(40.0)
    assert summary["cost_profile"] == "paper_current_taker"
    assert summary["taker_taker_round_trip_fee_bps"] == pytest.approx(80.0)


def test_unknown_cost_profile_fails_closed():
    with pytest.raises(ValueError, match="unknown cost profile"):
        get_cost_profile("cheap_for_profit")
