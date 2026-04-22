import math

from autobot.v2.main_async import AutoBotV2Async, _build_grid_config


def test_build_grid_config_legacy_defaults(monkeypatch):
    monkeypatch.setattr("autobot.v2.main_async._pair_registry", None)
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
