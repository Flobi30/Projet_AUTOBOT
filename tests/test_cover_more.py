import sys, os
import pytest

# 1) Vérifie que src/ est bien dans sys.path (via conftest.py)
def test_src_in_path():
    root = os.path.abspath(os.path.dirname(__file__) + os.sep + '..')
    assert os.path.join(root, 'src') in sys.path

# 2) Providers : couverture des cas succès et erreur
from data.providers import AlphaVantageProvider, TwelveDataProvider

@pytest.mark.parametrize("Cls", [AlphaVantageProvider, TwelveDataProvider])
def test_provider_returns_data(monkeypatch, Cls):
    data = {"a": 1}
    # stub _fetch pour renvoyer data
    monkeypatch.setattr(Cls, "_fetch", lambda self, sym: data)
    assert Cls().get_time_series("X") is data

@pytest.mark.parametrize("Cls", [AlphaVantageProvider, TwelveDataProvider])
def test_provider_empty_on_error(monkeypatch, Cls):
    # stub _fetch pour lever une exception
    monkeypatch.setattr(Cls, "_fetch", lambda self, *a, **k: (_ for _ in ()).throw(ValueError()))
    assert Cls().get_time_series("X") == {}

# 3) ExampleStrategy : test optionnel sur description
from strategies import ExampleStrategy

def test_example_strategy_description():
    inst = ExampleStrategy("n")
    if hasattr(inst, "description"):
        assert isinstance(inst.description, str)

# 4) RLModule : test de l’attribut name et de greet()
from autobot.rl import RLModule

def test_rlmodule_name_and_greet():
    m = RLModule("Z")
    assert hasattr(m, "name")
    assert m.name == "Z"
    assert hasattr(m, "greet")
    assert m.greet() == "Welcome to the Z Reinforcement Learning Module"
