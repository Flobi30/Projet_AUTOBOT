import pytest

import math
import os

from autobot.v2.main_async import AutoBotV2Async, _build_grid_config, _default_runtime_log_file


pytestmark = pytest.mark.unit

def test_build_grid_config_legacy_defaults(monkeypatch):
    monkeypatch.setattr("autobot.v2.main_async._research_grid_registry", lambda: None)
    config = _build_grid_config("XXBTZEUR")
    assert config == {"range_percent": 2.0, "num_levels": 20}


def test_create_all_instance_configs_zero_capital(monkeypatch):
    monkeypatch.delenv("TRADING_PAIRS", raising=False)
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR")
    monkeypatch.setenv("INITIAL_CAPITAL", "0")

    bot = AutoBotV2Async()
    configs = bot._create_all_instance_configs()

    assert len(configs) == 2
    assert all(cfg.initial_capital == 0.0 for cfg in configs)


def test_create_all_instance_configs_negative_capital(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR,ADAEUR")
    monkeypatch.setenv("INITIAL_CAPITAL", "-500")

    bot = AutoBotV2Async()
    configs = bot._create_all_instance_configs()

    assert len(configs) == 3
    assert all(cfg.initial_capital == 0.0 for cfg in configs)


def test_create_all_instance_configs_investable_sum_matches_total_minus_cash_reserve(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR,ADAEUR")
    monkeypatch.setenv("INITIAL_CAPITAL", "1000")

    bot = AutoBotV2Async()
    configs = bot._create_all_instance_configs()

    total_allocated = sum(cfg.initial_capital for cfg in configs)
    assert math.isclose(total_allocated, 800.0, abs_tol=0.02)


def test_create_all_instance_configs_legacy_priority_order(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR,ADAEUR")
    monkeypatch.setenv("INITIAL_CAPITAL", "1000")

    bot = AutoBotV2Async()
    configs = bot._create_all_instance_configs()

    by_symbol = {cfg.symbol: cfg.initial_capital for cfg in configs}
    assert by_symbol["XXBTZEUR"] > by_symbol["XETHZEUR"] > by_symbol["ADAEUR"]


def test_create_all_instance_configs_uses_observation_only_not_grid(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR,TRXEUR")
    monkeypatch.setenv("INITIAL_CAPITAL", "500")

    configs = AutoBotV2Async()._create_all_instance_configs()

    assert all(config.strategy == "observation_only" for config in configs)
    assert all(config.grid_config is None for config in configs)


def test_instance_factory_does_not_construct_archived_grid_registry(monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXBTZEUR,XETHZEUR")

    def unexpected_grid_registry_load():
        raise AssertionError("Grid registry must not load in the active runtime factory")

    monkeypatch.setattr(
        "autobot.v2.strategies.adaptive_grid_config.get_default_registry",
        unexpected_grid_registry_load,
    )

    configs = AutoBotV2Async()._create_all_instance_configs()

    assert len(configs) == 2
    assert all(config.strategy == "observation_only" for config in configs)


def test_main_async_default_log_path_is_not_the_read_only_container_root(monkeypatch):
    monkeypatch.delenv("AUTOBOT_LOG_FILE", raising=False)

    # The production image overrides this with /app/logs/...; the local
    # default remains writable beneath the process working directory.
    assert _default_runtime_log_file() == "logs/autobot_async.log"
    assert callable(AutoBotV2Async.stop)


def test_observation_runtime_does_not_retain_private_exchange_credentials(monkeypatch):
    monkeypatch.setenv("AUTOBOT_OBSERVATION_ONLY_RUNTIME", "true")
    monkeypatch.setenv("KRAKEN_API_KEY", "must-not-be-retained")
    monkeypatch.setenv("KRAKEN_API_SECRET", "must-not-be-retained")

    bot = AutoBotV2Async(
        api_key="must-not-be-retained",
        api_secret="must-not-be-retained",
    )

    assert bot.api_key is None
    assert bot.api_secret is None
    assert "KRAKEN_API_KEY" not in os.environ
    assert "KRAKEN_API_SECRET" not in os.environ
