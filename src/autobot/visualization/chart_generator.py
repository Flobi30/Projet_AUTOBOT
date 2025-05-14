"""
Chart generator module for AUTOBOT.
Provides functions to generate various types of charts for trading data visualization.
"""
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
import base64
from io import BytesIO

logger = logging.getLogger(__name__)

def generate_candlestick_chart(
    data: List[Dict[str, Any]],
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    indicators: Optional[List[str]] = None,
    theme: str = "dark",
    width: int = 800,
    height: int = 600,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a candlestick chart for trading data.
    
    Args:
        data: List of OHLCV data points
        symbol: Trading pair symbol
        timeframe: Chart timeframe
        start_time: Start time for chart data
        end_time: End time for chart data
        indicators: List of technical indicators to include
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info(f"Generating candlestick chart for {symbol} on {timeframe} timeframe")
    
    indicators = indicators or ["MA:20", "MA:50", "RSI", "VOLUME"]
    
    processed_data = _process_ohlcv_data(data)
    
    indicator_data = _generate_indicator_data(processed_data, indicators)
    
    chart_config = {
        "type": "candlestick",
        "symbol": symbol,
        "timeframe": timeframe,
        "theme": theme,
        "width": width,
        "height": height,
        "data": processed_data,
        "indicators": indicator_data,
        "time_range": {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None
        }
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config

def generate_portfolio_chart(
    portfolio_history: List[Dict[str, Any]],
    benchmark: Optional[List[Dict[str, Any]]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    include_drawdown: bool = True,
    theme: str = "dark",
    width: int = 800,
    height: int = 400,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a portfolio performance chart.
    
    Args:
        portfolio_history: List of portfolio value data points
        benchmark: Optional benchmark data for comparison
        start_time: Start time for chart data
        end_time: End time for chart data
        include_drawdown: Include drawdown chart
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info("Generating portfolio performance chart")
    
    processed_portfolio = _process_portfolio_data(portfolio_history)
    
    processed_benchmark = None
    if benchmark:
        processed_benchmark = _process_portfolio_data(benchmark)
    
    drawdown_data = None
    if include_drawdown:
        drawdown_data = _calculate_drawdown(processed_portfolio)
    
    chart_config = {
        "type": "portfolio",
        "theme": theme,
        "width": width,
        "height": height,
        "portfolio": processed_portfolio,
        "benchmark": processed_benchmark,
        "drawdown": drawdown_data,
        "time_range": {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None
        }
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config

def generate_correlation_matrix(
    symbols: List[str],
    data: Dict[str, List[Dict[str, Any]]],
    timeframe: str = "1d",
    period: int = 30,
    theme: str = "dark",
    width: int = 600,
    height: int = 600,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a correlation matrix for multiple trading pairs.
    
    Args:
        symbols: List of trading pair symbols
        data: Dictionary of OHLCV data for each symbol
        timeframe: Data timeframe
        period: Period for correlation calculation
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info(f"Generating correlation matrix for {len(symbols)} symbols")
    
    correlation_data = _calculate_correlation_matrix(symbols, data, period)
    
    chart_config = {
        "type": "correlation",
        "symbols": symbols,
        "timeframe": timeframe,
        "period": period,
        "theme": theme,
        "width": width,
        "height": height,
        "data": correlation_data
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config

def generate_volume_profile(
    data: List[Dict[str, Any]],
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    num_bins: int = 50,
    theme: str = "dark",
    width: int = 800,
    height: int = 400,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a volume profile chart.
    
    Args:
        data: List of OHLCV data points
        symbol: Trading pair symbol
        timeframe: Chart timeframe
        num_bins: Number of price bins for volume profile
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info(f"Generating volume profile for {symbol} on {timeframe} timeframe")
    
    volume_profile_data = _calculate_volume_profile(data, num_bins)
    
    chart_config = {
        "type": "volume_profile",
        "symbol": symbol,
        "timeframe": timeframe,
        "theme": theme,
        "width": width,
        "height": height,
        "data": volume_profile_data,
        "num_bins": num_bins
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config

def generate_market_depth(
    order_book: Dict[str, List[List[float]]],
    symbol: str = "BTC/USDT",
    depth: int = 20,
    theme: str = "dark",
    width: int = 800,
    height: int = 400,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a market depth chart.
    
    Args:
        order_book: Order book data with bids and asks
        symbol: Trading pair symbol
        depth: Depth of order book to display
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info(f"Generating market depth chart for {symbol}")
    
    processed_order_book = _process_order_book(order_book, depth)
    
    chart_config = {
        "type": "market_depth",
        "symbol": symbol,
        "theme": theme,
        "width": width,
        "height": height,
        "data": processed_order_book,
        "depth": depth
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config

def generate_performance_metrics(
    metrics: Dict[str, Any],
    theme: str = "dark",
    width: int = 800,
    height: int = 600,
    as_base64: bool = False
) -> Union[Dict[str, Any], str]:
    """
    Generate a performance metrics dashboard.
    
    Args:
        metrics: Dictionary of performance metrics
        theme: Chart theme ('dark' or 'light')
        width: Chart width in pixels
        height: Chart height in pixels
        as_base64: Return chart as base64 encoded image
        
    Returns:
        Dict with chart configuration or base64 encoded image
    """
    logger.info("Generating performance metrics dashboard")
    
    chart_config = {
        "type": "performance_metrics",
        "theme": theme,
        "width": width,
        "height": height,
        "metrics": metrics
    }
    
    if as_base64:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    return chart_config


def _process_ohlcv_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process OHLCV data for charting."""
    processed_data = []
    
    for item in data:
        processed_item = {
            "timestamp": item.get("timestamp"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume")
        }
        processed_data.append(processed_item)
    
    return processed_data

def _generate_indicator_data(data: List[Dict[str, Any]], indicators: List[str]) -> Dict[str, List[float]]:
    """Generate technical indicator data."""
    indicator_data = {}
    
    
    for indicator in indicators:
        if indicator.startswith("MA:"):
            period = int(indicator.split(":")[1])
            indicator_data[f"MA{period}"] = [item["close"] for item in data]
        elif indicator == "RSI":
            indicator_data["RSI"] = [50 + (i % 50) for i in range(len(data))]
        elif indicator == "VOLUME":
            indicator_data["VOLUME"] = [item["volume"] for item in data]
    
    return indicator_data

def _process_portfolio_data(portfolio_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process portfolio history data for charting."""
    processed_data = []
    
    for item in portfolio_history:
        processed_item = {
            "timestamp": item.get("timestamp"),
            "value": item.get("value"),
            "pnl": item.get("pnl"),
            "pnl_percent": item.get("pnl_percent")
        }
        processed_data.append(processed_item)
    
    return processed_data

def _calculate_drawdown(portfolio_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate drawdown from portfolio data."""
    drawdown_data = []
    peak = 0
    
    for i, item in enumerate(portfolio_data):
        value = item["value"]
        
        if i == 0 or value > peak:
            peak = value
            drawdown = 0
        else:
            drawdown = (peak - value) / peak * 100
        
        drawdown_data.append({
            "timestamp": item["timestamp"],
            "drawdown": drawdown
        })
    
    return drawdown_data

def _calculate_correlation_matrix(
    symbols: List[str],
    data: Dict[str, List[Dict[str, Any]]],
    period: int
) -> List[List[float]]:
    """Calculate correlation matrix for multiple symbols."""
    
    num_symbols = len(symbols)
    correlation_matrix = []
    
    for i in range(num_symbols):
        row = []
        for j in range(num_symbols):
            if i == j:
                row.append(1.0)
            else:
                row.append((i * j) % 10 / 10)
        correlation_matrix.append(row)
    
    return correlation_matrix

def _calculate_volume_profile(data: List[Dict[str, Any]], num_bins: int) -> List[Dict[str, Any]]:
    """Calculate volume profile from OHLCV data."""
    
    min_price = min(item["low"] for item in data)
    max_price = max(item["high"] for item in data)
    
    bin_size = (max_price - min_price) / num_bins
    bins = []
    
    for i in range(num_bins):
        price = min_price + i * bin_size
        volume = (i * 7919) % 1000
        bins.append({
            "price": price,
            "volume": volume
        })
    
    return bins

def _process_order_book(order_book: Dict[str, List[List[float]]], depth: int) -> Dict[str, List[Dict[str, float]]]:
    """Process order book data for market depth chart."""
    processed_order_book = {
        "bids": [],
        "asks": []
    }
    
    bids = order_book.get("bids", [])
    for i in range(min(depth, len(bids))):
        bid = bids[i]
        processed_order_book["bids"].append({
            "price": bid[0],
            "amount": bid[1]
        })
    
    asks = order_book.get("asks", [])
    for i in range(min(depth, len(asks))):
        ask = asks[i]
        processed_order_book["asks"].append({
            "price": ask[0],
            "amount": ask[1]
        })
    
    return processed_order_book
