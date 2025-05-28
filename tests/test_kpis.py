import pytest
from autobot.ecommerce.kpis import calculate_profit_margin, get_sales_kpis

def test_calculate_profit_margin():
    assert calculate_profit_margin(100, 50) == pytest.approx(0.5)

def test_calculate_profit_margin_zero_revenue():
    assert calculate_profit_margin(0, 50) == 0.0

def test_get_sales_kpis():
    sales_data = [
        {'amount': 200, 'profit': 50},
        {'amount': 300, 'profit': 75},
    ]
    kpis = get_sales_kpis(sales_data)
    assert kpis['total_sales']  == 500
    assert kpis['total_profit'] == 125
    assert kpis['count']        == 2
