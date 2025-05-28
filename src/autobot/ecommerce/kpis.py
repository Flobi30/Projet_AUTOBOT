# File: src/autobot/ecommerce/kpis.py

from typing import List, Dict

def calculate_profit_margin(revenue: float, cost: float) -> float:
    """Calculate profit margin given revenue and cost."""
    if revenue == 0:
        return 0.0
    return (revenue - cost) / revenue

def get_sales_kpis(sales_data: List[Dict[str, float]]) -> Dict[str, float]:
    """Calculate total sales, profit, cost, profit_margin, and count from sales data."""
    total_sales = sum(item.get("amount", 0) for item in sales_data)
    total_profit = sum(item.get("profit", 0) for item in sales_data)
    total_cost = total_sales - total_profit
    profit_margin = calculate_profit_margin(total_sales, total_cost)
    count = len(sales_data)
    return {
        "total_sales": total_sales,
        "total_profit": total_profit,
        "total_cost": total_cost,
        "profit_margin": profit_margin,
        "count": count
    }

def get_kpis() -> dict:
    """Placeholder for general e-commerce KPIs."""
    return {
        "total_sales": 12345.67,
        "conversion_rate": 2.34,
        "avg_order_value": 78.90
    }
