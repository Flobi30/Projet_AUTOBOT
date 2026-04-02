"""
Market configurations for AUTOBOT V2
Multi-market support: Crypto, Forex, Commodities
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

class MarketType(Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITY = "commodity"

@dataclass
class MarketConfig:
    """Configuration for a specific market"""
    symbol: str  # Kraken symbol (e.g., XXBTZEUR, EURUSD)
    market_type: MarketType
    min_volume: float  # Minimum order size
    max_leverage: int
    trading_hours: str  # "24/7", "24/5", "23/24"
    decimal_places: int  # Price precision
    # Grid strategy defaults
    default_grid_range: float  # 7.0 for crypto, 1.0 for forex
    default_grid_step: float   # 1.0 for crypto, 0.1 for forex
    pip_value: Optional[float] = None  # For forex (0.0001 for most pairs)
    contract_size: Optional[float] = None  # For commodities


# Market configurations
MARKETS: Dict[str, MarketConfig] = {
    # Crypto
    "BTC/EUR": MarketConfig(
        symbol="XXBTZEUR",
        market_type=MarketType.CRYPTO,
        min_volume=0.0001,
        max_leverage=3,
        trading_hours="24/7",
        decimal_places=1,
        default_grid_range=7.0,
        default_grid_step=1.0
    ),
    "ETH/EUR": MarketConfig(
        symbol="XETHZEUR",
        market_type=MarketType.CRYPTO,
        min_volume=0.001,
        max_leverage=3,
        trading_hours="24/7",
        decimal_places=2,
        default_grid_range=7.0,
        default_grid_step=1.0
    ),
    
    # Forex
    "EUR/USD": MarketConfig(
        symbol="EURUSD",
        market_type=MarketType.FOREX,
        min_volume=10.0,  # 10 units (micro-lot)
        max_leverage=30,
        trading_hours="24/5",
        decimal_places=5,
        pip_value=0.0001,
        default_grid_range=1.0,  # 1% range for forex
        default_grid_step=0.1    # 0.1% steps
    ),
    "GBP/USD": MarketConfig(
        symbol="GBPUSD",
        market_type=MarketType.FOREX,
        min_volume=10.0,
        max_leverage=30,
        trading_hours="24/5",
        decimal_places=5,
        pip_value=0.0001,
        default_grid_range=1.0,
        default_grid_step=0.1
    ),
    "USD/JPY": MarketConfig(
        symbol="USDJPY",
        market_type=MarketType.FOREX,
        min_volume=10.0,
        max_leverage=30,
        trading_hours="24/5",
        decimal_places=3,
        pip_value=0.01,  # JPY pairs use 2 decimal pips
        default_grid_range=1.0,
        default_grid_step=0.1
    ),
    
    # Commodities (via PAXG on Kraken - tokenized gold)
    "GOLD/EUR": MarketConfig(
        symbol="PAXGZEUR",
        market_type=MarketType.COMMODITY,
        min_volume=0.001,  # PAXG is gold-backed token
        max_leverage=2,
        trading_hours="24/7",
        decimal_places=2,
        default_grid_range=3.0,  # Gold less volatile than crypto
        default_grid_step=0.5
    ),
}


def get_market_config(symbol: str) -> Optional[MarketConfig]:
    """Get configuration for a market symbol"""
    return MARKETS.get(symbol)


def is_market_open(symbol: str) -> bool:
    """Check if market is currently open for trading"""
    import datetime
    
    config = get_market_config(symbol)
    if not config:
        return True  # Unknown markets assumed open
    
    if config.trading_hours == "24/7":
        return True
    
    if config.trading_hours == "24/5":
        # Forex: closed weekends
        now = datetime.datetime.utcnow()
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        return True
    
    if config.trading_hours == "23/24":
        # Commodities: check specific hours
        now = datetime.datetime.utcnow()
        # Closed 10pm-11pm UTC typically
        if now.hour == 22:
            return False
        return True
    
    return True


def format_price(symbol: str, price: float) -> str:
    """Format price according to market decimal places"""
    config = get_market_config(symbol)
    if config:
        return f"{price:.{config.decimal_places}f}"
    return str(price)


def calculate_pip_value(symbol: str, volume: float, price: float) -> float:
    """Calculate pip value for position sizing"""
    config = get_market_config(symbol)
    if not config or not config.pip_value:
        return 0.0
    
    # For forex: 1 pip = 0.0001 (or 0.01 for JPY)
    # Value = volume * pip_size
    return volume * config.pip_value
