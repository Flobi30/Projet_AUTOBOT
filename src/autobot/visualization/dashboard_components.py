"""
Dashboard components module for AUTOBOT.
Provides functions to create dashboard components for the trading interface.
"""
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def create_trading_dashboard(
    portfolio_data: Dict[str, Any],
    market_data: Dict[str, Any],
    open_positions: List[Dict[str, Any]],
    recent_trades: List[Dict[str, Any]],
    performance_metrics: Dict[str, Any],
    theme: str = "dark"
) -> Dict[str, Any]:
    """
    Create a complete trading dashboard.
    
    Args:
        portfolio_data: Portfolio performance data
        market_data: Market overview data
        open_positions: List of open positions
        recent_trades: List of recent trades
        performance_metrics: Trading performance metrics
        theme: Dashboard theme ('dark' or 'light')
        
    Returns:
        Dict with dashboard configuration
    """
    logger.info("Creating trading dashboard")
    
    portfolio_component = create_portfolio_summary(portfolio_data, theme=theme)
    market_component = create_market_overview(market_data, theme=theme)
    positions_component = _create_positions_component(open_positions, theme=theme)
    trades_component = _create_trades_component(recent_trades, theme=theme)
    performance_component = create_strategy_performance(performance_metrics, theme=theme)
    
    dashboard = {
        "type": "dashboard",
        "theme": theme,
        "layout": "grid",
        "components": [
            {
                "id": "portfolio",
                "title": "Portfolio Summary",
                "position": {"row": 0, "col": 0, "width": 6, "height": 4},
                "content": portfolio_component
            },
            {
                "id": "market",
                "title": "Market Overview",
                "position": {"row": 0, "col": 6, "width": 6, "height": 4},
                "content": market_component
            },
            {
                "id": "positions",
                "title": "Open Positions",
                "position": {"row": 4, "col": 0, "width": 6, "height": 4},
                "content": positions_component
            },
            {
                "id": "trades",
                "title": "Recent Trades",
                "position": {"row": 4, "col": 6, "width": 6, "height": 4},
                "content": trades_component
            },
            {
                "id": "performance",
                "title": "Strategy Performance",
                "position": {"row": 8, "col": 0, "width": 12, "height": 6},
                "content": performance_component
            }
        ]
    }
    
    return dashboard

def create_market_overview(
    market_data: Dict[str, Any],
    num_pairs: int = 10,
    include_charts: bool = True,
    theme: str = "dark"
) -> Dict[str, Any]:
    """
    Create a market overview component.
    
    Args:
        market_data: Market data for multiple trading pairs
        num_pairs: Number of trading pairs to display
        include_charts: Include mini charts for each pair
        theme: Component theme ('dark' or 'light')
        
    Returns:
        Dict with component configuration
    """
    logger.info(f"Creating market overview component with {num_pairs} pairs")
    
    pairs = market_data.get("pairs", [])[:num_pairs]
    processed_pairs = []
    
    for pair in pairs:
        processed_pair = {
            "symbol": pair.get("symbol"),
            "last_price": pair.get("last_price"),
            "change_24h": pair.get("change_24h"),
            "volume_24h": pair.get("volume_24h"),
            "high_24h": pair.get("high_24h"),
            "low_24h": pair.get("low_24h")
        }
        
        if include_charts and "chart_data" in pair:
            processed_pair["chart"] = _create_mini_chart(pair["chart_data"], theme)
            
        processed_pairs.append(processed_pair)
    
    component = {
        "type": "market_overview",
        "theme": theme,
        "pairs": processed_pairs,
        "global_metrics": {
            "total_market_cap": market_data.get("total_market_cap"),
            "total_volume_24h": market_data.get("total_volume_24h"),
            "btc_dominance": market_data.get("btc_dominance")
        }
    }
    
    return component

def create_portfolio_summary(
    portfolio_data: Dict[str, Any],
    include_chart: bool = True,
    include_assets: bool = True,
    theme: str = "dark"
) -> Dict[str, Any]:
    """
    Create a portfolio summary component.
    
    Args:
        portfolio_data: Portfolio performance data
        include_chart: Include portfolio performance chart
        include_assets: Include breakdown of assets
        theme: Component theme ('dark' or 'light')
        
    Returns:
        Dict with component configuration
    """
    logger.info("Creating portfolio summary component")
    
    component = {
        "type": "portfolio_summary",
        "theme": theme,
        "total_value": portfolio_data.get("total_value"),
        "pnl_24h": portfolio_data.get("pnl_24h"),
        "pnl_24h_percent": portfolio_data.get("pnl_24h_percent"),
        "pnl_total": portfolio_data.get("pnl_total"),
        "pnl_total_percent": portfolio_data.get("pnl_total_percent")
    }
    
    if include_chart and "history" in portfolio_data:
        component["chart"] = _create_portfolio_chart(portfolio_data["history"], theme)
    
    if include_assets and "assets" in portfolio_data:
        component["assets"] = _process_portfolio_assets(portfolio_data["assets"])
    
    return component

def create_strategy_performance(
    performance_metrics: Dict[str, Any],
    include_charts: bool = True,
    include_trades: bool = True,
    theme: str = "dark"
) -> Dict[str, Any]:
    """
    Create a strategy performance component.
    
    Args:
        performance_metrics: Strategy performance metrics
        include_charts: Include performance charts
        include_trades: Include trade statistics
        theme: Component theme ('dark' or 'light')
        
    Returns:
        Dict with component configuration
    """
    logger.info("Creating strategy performance component")
    
    component = {
        "type": "strategy_performance",
        "theme": theme,
        "metrics": {
            "sharpe_ratio": performance_metrics.get("sharpe_ratio"),
            "sortino_ratio": performance_metrics.get("sortino_ratio"),
            "max_drawdown": performance_metrics.get("max_drawdown"),
            "win_rate": performance_metrics.get("win_rate"),
            "profit_factor": performance_metrics.get("profit_factor"),
            "expectancy": performance_metrics.get("expectancy"),
            "avg_trade": performance_metrics.get("avg_trade"),
            "avg_win": performance_metrics.get("avg_win"),
            "avg_loss": performance_metrics.get("avg_loss"),
            "best_trade": performance_metrics.get("best_trade"),
            "worst_trade": performance_metrics.get("worst_trade"),
            "recovery_factor": performance_metrics.get("recovery_factor"),
            "calmar_ratio": performance_metrics.get("calmar_ratio")
        }
    }
    
    if include_charts and "equity_curve" in performance_metrics:
        component["equity_chart"] = _create_equity_curve_chart(
            performance_metrics["equity_curve"],
            theme
        )
        
        if "drawdown_curve" in performance_metrics:
            component["drawdown_chart"] = _create_drawdown_chart(
                performance_metrics["drawdown_curve"],
                theme
            )
    
    if include_trades and "trade_stats" in performance_metrics:
        component["trade_stats"] = performance_metrics["trade_stats"]
    
    return component


def _create_mini_chart(chart_data: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create a mini chart configuration."""
    return {
        "type": "sparkline",
        "theme": theme,
        "data": chart_data,
        "width": 120,
        "height": 40
    }

def _create_portfolio_chart(history_data: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create a portfolio chart configuration."""
    return {
        "type": "line",
        "theme": theme,
        "data": history_data,
        "width": 400,
        "height": 200,
        "show_x_axis": True,
        "show_y_axis": True,
        "show_tooltip": True
    }

def _process_portfolio_assets(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process portfolio assets data."""
    processed_assets = []
    
    for asset in assets:
        processed_asset = {
            "symbol": asset.get("symbol"),
            "amount": asset.get("amount"),
            "value": asset.get("value"),
            "allocation": asset.get("allocation"),
            "pnl": asset.get("pnl"),
            "pnl_percent": asset.get("pnl_percent")
        }
        processed_assets.append(processed_asset)
    
    return processed_assets

def _create_positions_component(positions: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create an open positions component."""
    return {
        "type": "positions_table",
        "theme": theme,
        "positions": positions,
        "columns": [
            {"id": "symbol", "name": "Symbol"},
            {"id": "side", "name": "Side"},
            {"id": "entry_price", "name": "Entry Price"},
            {"id": "current_price", "name": "Current Price"},
            {"id": "amount", "name": "Amount"},
            {"id": "value", "name": "Value"},
            {"id": "pnl", "name": "P&L"},
            {"id": "pnl_percent", "name": "P&L %"}
        ]
    }

def _create_trades_component(trades: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create a recent trades component."""
    return {
        "type": "trades_table",
        "theme": theme,
        "trades": trades,
        "columns": [
            {"id": "timestamp", "name": "Time"},
            {"id": "symbol", "name": "Symbol"},
            {"id": "side", "name": "Side"},
            {"id": "price", "name": "Price"},
            {"id": "amount", "name": "Amount"},
            {"id": "value", "name": "Value"},
            {"id": "fee", "name": "Fee"}
        ]
    }

def _create_equity_curve_chart(equity_data: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create an equity curve chart configuration."""
    return {
        "type": "line",
        "theme": theme,
        "data": equity_data,
        "width": 800,
        "height": 300,
        "show_x_axis": True,
        "show_y_axis": True,
        "show_tooltip": True,
        "show_legend": True
    }

def _create_drawdown_chart(drawdown_data: List[Dict[str, Any]], theme: str) -> Dict[str, Any]:
    """Create a drawdown chart configuration."""
    return {
        "type": "area",
        "theme": theme,
        "data": drawdown_data,
        "width": 800,
        "height": 150,
        "show_x_axis": True,
        "show_y_axis": True,
        "show_tooltip": True,
        "fill_opacity": 0.5,
        "color": "#ff3333"
    }
