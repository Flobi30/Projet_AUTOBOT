import sys, os
import pytest

# 1) Vérification conftest.py a bien ajouté src/ en sys.path
#    on doit pouvoir importer autobot

def test_conftest_path():
    root = os.path.abspath(os.path.dirname(__file__) + os.sep + "..")
    src  = os.path.join(root, "src")
    assert src in sys.path, f"Le dossier src/ ({src}) doit être dans sys.path"

# 2) Data providers: branche succès et fallback
from data.providers import AlphaVantageProvider, TwelveDataProvider

@pytest.mark.parametrize("ProviderClass", [AlphaVantageProvider, TwelveDataProvider])
def test_provider_success(monkeypatch, ProviderClass):
    dummy = {"time": [1,2,3]}
    # stub _fetch pour renvoyer dummy data
    monkeypatch.setattr(ProviderClass, "_fetch", lambda self, symbol: dummy)
    assert ProviderClass().get_time_series("SYM") is dummy

@pytest.mark.parametrize("ProviderClass", [AlphaVantageProvider, TwelveDataProvider])
def test_provider_fallback(monkeypatch, ProviderClass):
    # stub _fetch pour lever une exception
    def raise_exc(self, *args, **kwargs):
        raise RuntimeError("fetch error")
    monkeypatch.setattr(ProviderClass, "_fetch", raise_exc)
    # en fallback, get_time_series retourne un dict vide
    assert ProviderClass().get_time_series("SYM") == {}

# 3) Strategies: StrategyManager.get et select_strategy
from strategies import StrategyManager, ExampleStrategy, select_strategy

def test_strategy_manager_get_known():
    sm = StrategyManager({"ex": ExampleStrategy})
    assert sm.get("ex") is ExampleStrategy

@pytest.mark.parametrize("name", ["ex", None, ""])
def test_select_strategy(monkeypatch, name):
    sm = StrategyManager({"ex": ExampleStrategy})
    if name == "ex":
        assert select_strategy(name, sm) is ExampleStrategy
    else:
        with pytest.raises(ValueError):
            select_strategy(name, sm)

# 4) RLModule: tester greet
from autobot.rl import RLModule

def test_rlmodule_greet_and_name():
    m = RLModule("Bot")
    assert hasattr(m, "greet"), "RLModule doit avoir la méthode greet()"
    # greet doit contenir le nom
    assert "Bot" in m.greet()
