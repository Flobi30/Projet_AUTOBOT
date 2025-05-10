import pytest
from autobot.ecommerce.kpis import calculate_profit_margin

def test_calculate_profit_margin_zero_or_negative():
    assert calculate_profit_margin(0, 50) == pytest.approx(0.0)
    assert calculate_profit_margin(20, 50) == pytest.approx(-1.5)
