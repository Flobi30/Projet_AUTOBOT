"""
AUTOBOT Macro Indicator Manager

Retrieves and caches macro-economic indicators from various sources:
- CPI, PPI, Core CPI
- NFP (Non-Farm Payrolls)
- Interest rates (FED, BCE, BoE)
- FOMC decisions
- GDP, PMI
- VIX, DXY
- M2 money supply
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import os

logger = logging.getLogger(__name__)


class IndicatorSource(Enum):
    """Data sources for macro indicators"""
    FRED = "fred"
    YAHOO = "yahoo"
    CACHE = "cache"
    MANUAL = "manual"


@dataclass
class MacroIndicator:
    """A single macro-economic indicator"""
    name: str
    value: float
    previous_value: Optional[float] = None
    change_pct: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: IndicatorSource = IndicatorSource.CACHE
    unit: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "previous_value": self.previous_value,
            "change_pct": self.change_pct,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "unit": self.unit,
            "description": self.description,
        }


class MacroIndicatorManager:
    """
    Manages retrieval and caching of macro-economic indicators.
    
    Supports:
    - Automatic retrieval at regular intervals
    - Local caching to avoid API overload
    - Multiple data sources with fallback
    """
    
    # FRED series IDs for common indicators
    FRED_SERIES = {
        "cpi": "CPIAUCSL",
        "core_cpi": "CPILFESL",
        "ppi": "PPIACO",
        "fed_rate": "FEDFUNDS",
        "gdp": "GDP",
        "unemployment": "UNRATE",
        "m2": "M2SL",
        "treasury_10y": "DGS10",
        "treasury_2y": "DGS2",
    }
    
    # Yahoo Finance tickers for market indicators
    YAHOO_TICKERS = {
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "sp500": "^GSPC",
        "gold": "GC=F",
        "oil": "CL=F",
    }
    
    def __init__(self, cache_dir: str = "data/macro_cache"):
        self.cache_dir = cache_dir
        self.indicators: Dict[str, MacroIndicator] = {}
        self.cache_ttl = timedelta(hours=1)
        self._ensure_cache_dir()
        self._load_cache()
    
    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists"""
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _load_cache(self) -> None:
        """Load cached indicators from disk"""
        cache_file = os.path.join(self.cache_dir, "indicators.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    for name, ind_data in data.items():
                        self.indicators[name] = MacroIndicator(
                            name=ind_data["name"],
                            value=ind_data["value"],
                            previous_value=ind_data.get("previous_value"),
                            change_pct=ind_data.get("change_pct"),
                            timestamp=datetime.fromisoformat(ind_data["timestamp"]),
                            source=IndicatorSource(ind_data.get("source", "cache")),
                            unit=ind_data.get("unit", ""),
                            description=ind_data.get("description", ""),
                        )
                logger.info(f"Loaded {len(self.indicators)} cached indicators")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
    
    def _save_cache(self) -> None:
        """Save indicators to cache"""
        cache_file = os.path.join(self.cache_dir, "indicators.json")
        try:
            data = {name: ind.to_dict() for name, ind in self.indicators.items()}
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def get_indicator(self, name: str) -> Optional[MacroIndicator]:
        """Get a specific indicator by name"""
        return self.indicators.get(name)
    
    def get_all_indicators(self) -> Dict[str, MacroIndicator]:
        """Get all cached indicators"""
        return self.indicators.copy()
    
    def update_indicator(
        self,
        name: str,
        value: float,
        previous_value: Optional[float] = None,
        source: IndicatorSource = IndicatorSource.MANUAL,
        unit: str = "",
        description: str = "",
    ) -> MacroIndicator:
        """Update or create an indicator"""
        change_pct = None
        if previous_value is not None and previous_value != 0:
            change_pct = ((value - previous_value) / abs(previous_value)) * 100
        
        indicator = MacroIndicator(
            name=name,
            value=value,
            previous_value=previous_value,
            change_pct=change_pct,
            timestamp=datetime.utcnow(),
            source=source,
            unit=unit,
            description=description,
        )
        
        self.indicators[name] = indicator
        self._save_cache()
        
        return indicator
    
    async def fetch_fred_indicator(self, indicator_name: str) -> Optional[MacroIndicator]:
        """
        Fetch indicator from FRED API.
        
        Note: Requires FRED API key to be configured.
        """
        if indicator_name not in self.FRED_SERIES:
            logger.warning(f"Unknown FRED indicator: {indicator_name}")
            return None
        
        series_id = self.FRED_SERIES[indicator_name]
        
        try:
            from autobot.providers.fred import get_time_series
            data = get_time_series(series_id)
            
            if data and len(data) > 0:
                latest = data[-1] if isinstance(data, list) else data
                value = float(latest.get("value", 0))
                previous = float(data[-2].get("value", 0)) if len(data) > 1 else None
                
                return self.update_indicator(
                    name=indicator_name,
                    value=value,
                    previous_value=previous,
                    source=IndicatorSource.FRED,
                    description=f"FRED series: {series_id}",
                )
        except Exception as e:
            logger.error(f"Failed to fetch FRED indicator {indicator_name}: {e}")
        
        return None
    
    async def refresh_all(self) -> Dict[str, MacroIndicator]:
        """Refresh all indicators from their sources"""
        # For now, return cached data
        # Full implementation would fetch from FRED, Yahoo, etc.
        return self.indicators
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of current macro conditions"""
        return {
            "indicator_count": len(self.indicators),
            "last_update": max(
                (ind.timestamp for ind in self.indicators.values()),
                default=datetime.utcnow()
            ).isoformat(),
            "indicators": {
                name: {
                    "value": ind.value,
                    "change_pct": ind.change_pct,
                }
                for name, ind in self.indicators.items()
            },
        }
