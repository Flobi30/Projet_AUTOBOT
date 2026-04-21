import importlib


def _reload_config(monkeypatch, env: dict[str, str]):
    keys = [
        "ENABLE_UNIVERSE_MANAGER",
        "ENABLE_PAIR_RANKING_ENGINE",
        "ENABLE_SCALABILITY_GUARD",
        "ENABLE_INSTANCE_ACTIVATION_MANAGER",
        "ENABLE_PORTFOLIO_ALLOCATOR",
        "ENABLE_DECISION_JOURNAL",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import autobot.v2.config as config
    return importlib.reload(config)


def test_flag_matrix_all_off_preserves_legacy_defaults(monkeypatch):
    c = _reload_config(monkeypatch, {})
    assert c.ENABLE_UNIVERSE_MANAGER is False
    assert c.ENABLE_PAIR_RANKING_ENGINE is False
    assert c.ENABLE_SCALABILITY_GUARD is False
    assert c.ENABLE_INSTANCE_ACTIVATION_MANAGER is False
    assert c.ENABLE_PORTFOLIO_ALLOCATOR is False
    assert c.ENABLE_DECISION_JOURNAL is False


def test_flag_matrix_independent_enable(monkeypatch):
    flags = [
        "ENABLE_UNIVERSE_MANAGER",
        "ENABLE_PAIR_RANKING_ENGINE",
        "ENABLE_SCALABILITY_GUARD",
        "ENABLE_INSTANCE_ACTIVATION_MANAGER",
        "ENABLE_PORTFOLIO_ALLOCATOR",
        "ENABLE_DECISION_JOURNAL",
    ]
    for flag in flags:
        c = _reload_config(monkeypatch, {flag: "true"})
        assert getattr(c, flag) is True
        for other in flags:
            if other != flag:
                assert getattr(c, other) is False


def test_flag_matrix_combined_safe_path(monkeypatch):
    c = _reload_config(
        monkeypatch,
        {
            "ENABLE_UNIVERSE_MANAGER": "true",
            "ENABLE_PAIR_RANKING_ENGINE": "true",
            "ENABLE_SCALABILITY_GUARD": "true",
            "ENABLE_INSTANCE_ACTIVATION_MANAGER": "true",
            "ENABLE_PORTFOLIO_ALLOCATOR": "true",
            "ENABLE_DECISION_JOURNAL": "true",
        },
    )
    assert c.ENABLE_UNIVERSE_MANAGER is True
    assert c.ENABLE_PAIR_RANKING_ENGINE is True
    assert c.ENABLE_SCALABILITY_GUARD is True
    assert c.ENABLE_INSTANCE_ACTIVATION_MANAGER is True
    assert c.ENABLE_PORTFOLIO_ALLOCATOR is True
    assert c.ENABLE_DECISION_JOURNAL is True
