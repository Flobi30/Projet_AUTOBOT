# tests/test_strategies.py
import pytest
from autobot.strategies import select_strategy, StrategyManager, ExampleStrategy

sm = StrategyManager({"example": ExampleStrategy})

def test_select_known():
    cls = select_strategy("example", sm)
    assert cls is ExampleStrategy

def test_select_unknown():
    with pytest.raises(ValueError):
        select_strategy("unknown", sm)

def test_empty_name():
    with pytest.raises(ValueError):
        select_strategy("", sm)
