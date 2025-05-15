"""
Automatic Hedging Module for AUTOBOT

This module provides functionality for automatically hedging trading positions
to protect against market movements. It supports various hedging strategies
including options, futures, and delta-neutral positions to minimize risk
while maintaining exposure to profitable opportunities.
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class HedgePosition:
    """Represents a hedge position"""
    
    def __init__(
        self,
        position_id: str,
        asset: str,
        hedge_type: str,
        size: float,
        entry_price: float,
        timestamp: Optional[float] = None,
        expiry: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a hedge position.
        
        Args:
            position_id: Original position ID being hedged
            asset: Asset symbol
            hedge_type: Type of hedge (e.g., "futures", "options", "spot")
            size: Position size
            entry_price: Entry price
            timestamp: Position timestamp
            expiry: Position expiry timestamp (for options/futures)
            metadata: Additional position metadata
        """
        self.position_id = position_id
        self.asset = asset
        self.hedge_type = hedge_type
        self.size = size
        self.entry_price = entry_price
        self.timestamp = timestamp or datetime.now().timestamp()
        self.expiry = expiry
        self.metadata = metadata or {}
        self.id = f"{position_id}_{hedge_type}_{int(self.timestamp)}"
        self.status = "active"
        self.exit_price = None
        self.exit_timestamp = None
        self.pnl = 0.0
    
    def close(self, exit_price: float, timestamp: Optional[float] = None):
        """
        Close the hedge position.
        
        Args:
            exit_price: Exit price
            timestamp: Exit timestamp
        """
        self.status = "closed"
        self.exit_price = exit_price
        self.exit_timestamp = timestamp or datetime.now().timestamp()
        
        if self.hedge_type == "futures" or self.hedge_type == "spot":
            if self.size < 0:
                self.pnl = (self.entry_price - exit_price) * abs(self.size)
            else:
                self.pnl = (exit_price - self.entry_price) * abs(self.size)
        
        elif self.hedge_type == "options":
            option_type = self.metadata.get("option_type", "put")
            strike_price = self.metadata.get("strike_price", self.entry_price)
            
            if option_type == "put":
                intrinsic_value = max(0, strike_price - exit_price)
                self.pnl = (intrinsic_value - self.entry_price) * abs(self.size)
            else:
                intrinsic_value = max(0, exit_price - strike_price)
                self.pnl = (intrinsic_value - self.entry_price) * abs(self.size)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert hedge position to dictionary"""
        result = {
            "id": self.id,
            "position_id": self.position_id,
            "asset": self.asset,
            "hedge_type": self.hedge_type,
            "size": self.size,
            "entry_price": self.entry_price,
            "timestamp": self.timestamp,
            "status": self.status,
            "metadata": self.metadata
        }
        
        if self.expiry:
            result["expiry"] = self.expiry
        
        if self.status == "closed":
            result["exit_price"] = self.exit_price
            result["exit_timestamp"] = self.exit_timestamp
            result["pnl"] = self.pnl
        
        return result


class HedgingStrategy:
    """Base class for hedging strategies"""
    
    def __init__(self, name: str):
        """
        Initialize hedging strategy.
        
        Args:
            name: Strategy name
        """
        self.name = name
    
    def calculate_hedge(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate hedge parameters for a position.
        
        Args:
            position: Position to hedge
            market_data: Market data for calculation
            
        Returns:
            Dict: Hedge parameters, or None if no hedge is needed
        """
        raise NotImplementedError("Subclasses must implement calculate_hedge")


class DeltaHedgeStrategy(HedgingStrategy):
    """Delta hedging strategy using futures or options"""
    
    def __init__(
        self,
        hedge_ratio: float = 1.0,
        prefer_options: bool = False,
        dynamic_adjustment: bool = True
    ):
        """
        Initialize delta hedging strategy.
        
        Args:
            hedge_ratio: Ratio of position to hedge (0-1)
            prefer_options: Whether to prefer options over futures
            dynamic_adjustment: Whether to dynamically adjust hedge ratio
        """
        super().__init__("delta_hedge")
        self.hedge_ratio = hedge_ratio
        self.prefer_options = prefer_options
        self.dynamic_adjustment = dynamic_adjustment
    
    def calculate_hedge(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate delta hedge for a position.
        
        Args:
            position: Position to hedge
            market_data: Market data for calculation
            
        Returns:
            Dict: Hedge parameters, or None if no hedge is needed
        """
        position_size = position.get("size", 0)
        position_direction = 1 if position_size > 0 else -1
        
        if abs(position_size) < 0.001:
            return None
        
        hedge_size = -position_size * self.hedge_ratio
        
        if self.dynamic_adjustment and "volatility" in market_data:
            volatility = market_data.get("volatility", 0.2)
            adjusted_ratio = min(1.0, self.hedge_ratio * (1 + volatility))
            hedge_size = -position_size * adjusted_ratio
        
        if self.prefer_options and "options_data" in market_data:
            hedge_type = "options"
            
            option_type = "put" if position_direction > 0 else "call"
            
            current_price = market_data.get("price", 0)
            strike_price = current_price
            
            options_data = market_data.get("options_data", {})
            option_premium = options_data.get(f"{option_type}_premium", current_price * 0.05)
            
            expiry = datetime.now().timestamp() + (30 * 24 * 60 * 60)
            
            return {
                "hedge_type": hedge_type,
                "size": abs(hedge_size),  # Options size is always positive
                "price": option_premium,
                "expiry": expiry,
                "metadata": {
                    "option_type": option_type,
                    "strike_price": strike_price
                }
            }
        else:
            hedge_type = "futures" if "futures_data" in market_data else "spot"
            current_price = market_data.get("price", 0)
            
            return {
                "hedge_type": hedge_type,
                "size": hedge_size,
                "price": current_price,
                "metadata": {}
            }


class OptionsHedgeStrategy(HedgingStrategy):
    """Options hedging strategy using puts and calls"""
    
    def __init__(
        self,
        hedge_ratio: float = 0.8,
        otm_percentage: float = 0.05,  # 5% out-of-the-money
        expiry_days: int = 30
    ):
        """
        Initialize options hedging strategy.
        
        Args:
            hedge_ratio: Ratio of position to hedge (0-1)
            otm_percentage: Percentage out-of-the-money for options
            expiry_days: Option expiry in days
        """
        super().__init__("options_hedge")
        self.hedge_ratio = hedge_ratio
        self.otm_percentage = otm_percentage
        self.expiry_days = expiry_days
    
    def calculate_hedge(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate options hedge for a position.
        
        Args:
            position: Position to hedge
            market_data: Market data for calculation
            
        Returns:
            Dict: Hedge parameters, or None if no hedge is needed
        """
        position_size = position.get("size", 0)
        position_direction = 1 if position_size > 0 else -1
        
        if abs(position_size) < 0.001 or "options_data" not in market_data:
            return None
        
        hedge_size = abs(position_size) * self.hedge_ratio
        
        option_type = "put" if position_direction > 0 else "call"
        
        current_price = market_data.get("price", 0)
        if option_type == "put":
            strike_price = current_price * (1 - self.otm_percentage)
        else:
            strike_price = current_price * (1 + self.otm_percentage)
        
        options_data = market_data.get("options_data", {})
        option_premium = options_data.get(f"{option_type}_premium", current_price * 0.03)
        
        expiry = datetime.now().timestamp() + (self.expiry_days * 24 * 60 * 60)
        
        return {
            "hedge_type": "options",
            "size": hedge_size,
            "price": option_premium,
            "expiry": expiry,
            "metadata": {
                "option_type": option_type,
                "strike_price": strike_price
            }
        }


class AutoHedging:
    """
    Automatic hedging module for protecting trading positions.
    
    Supports various hedging strategies including options, futures,
    and delta-neutral positions to minimize risk while maintaining
    exposure to profitable opportunities.
    """
    
    def __init__(
        self,
        autonomous_mode: bool = True,
        visible_interface: bool = True,
        check_interval: int = 60,  # 1 minute
        auto_hedge: bool = True,
        default_strategy: str = "delta_hedge",
        max_hedge_ratio: float = 1.0,
        hedge_threshold: float = 0.1  # 10% drawdown threshold
    ):
        """
        Initialize the auto hedging module.
        
        Args:
            autonomous_mode: Whether to operate in autonomous mode
            visible_interface: Whether to show detailed information in the interface
            check_interval: Interval between hedge checks (in seconds)
            auto_hedge: Whether to automatically hedge positions
            default_strategy: Default hedging strategy
            max_hedge_ratio: Maximum hedge ratio (0-1)
            hedge_threshold: Drawdown threshold for automatic hedging
        """
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.check_interval = check_interval
        self.auto_hedge = auto_hedge
        self.default_strategy = default_strategy
        self.max_hedge_ratio = max_hedge_ratio
        self.hedge_threshold = hedge_threshold
        
        self.positions = {}  # {position_id: position}
        self.hedges = {}  # {hedge_id: hedge}
        self.market_data = {}  # {asset: data}
        
        self.strategies = {
            "delta_hedge": DeltaHedgeStrategy(),
            "options_hedge": OptionsHedgeStrategy()
        }
        
        self._hedge_callbacks = []
        self._check_thread = None
        self._check_active = False
        
        # if self.autonomous_mode and self.auto_hedge:
        #     self._start_check_thread()
    
    def register_strategy(self, strategy: HedgingStrategy):
        """
        Register a hedging strategy.
        
        Args:
            strategy: Hedging strategy to register
        """
        self.strategies[strategy.name] = strategy
        
        if self.visible_interface:
            logger.info(f"Registered hedging strategy: {strategy.name}")
        else:
            logger.debug(f"Registered hedging strategy: {strategy.name}")
    
    def update_position(self, position: Dict[str, Any]):
        """
        Update a trading position.
        
        Args:
            position: Position data
        """
        position_id = position.get("id")
        if not position_id:
            logger.warning("Position has no ID, skipping")
            return
        
        self.positions[position_id] = position
        
        if self.autonomous_mode and self.auto_hedge:
            self._check_hedge_position(position_id)
    
    def update_market_data(self, asset: str, data: Dict[str, Any]):
        """
        Update market data for an asset.
        
        Args:
            asset: Asset symbol
            data: Market data
        """
        if asset not in self.market_data:
            self.market_data[asset] = {}
        
        self.market_data[asset].update(data)
        self.market_data[asset]["timestamp"] = datetime.now().timestamp()
        
        if self.autonomous_mode and self.auto_hedge:
            for position_id, position in self.positions.items():
                if position.get("asset") == asset:
                    self._check_hedge_position(position_id)
    
    def register_hedge_callback(self, callback: Callable[[HedgePosition], None]):
        """
        Register a callback to be called when a hedge is created or updated.
        
        Args:
            callback: Function to call when a hedge is created or updated
        """
        self._hedge_callbacks.append(callback)
    
    def _start_check_thread(self):
        """
        Start the background hedge check thread.
        """
        if self._check_thread is not None and self._check_thread.is_alive():
            return
        
        self._check_active = True
        self._check_thread = threading.Thread(
            target=self._check_loop,
            daemon=True
        )
        self._check_thread.start()
        
        if self.visible_interface:
            logger.info("Started auto hedging check thread")
        else:
            logger.debug("Started auto hedging check thread")
    
    def _check_loop(self):
        """
        Background loop for continuous hedge checking.
        """
        while self._check_active:
            try:
                for position_id in list(self.positions.keys()):
                    self._check_hedge_position(position_id)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in hedge check loop: {str(e)}")
                time.sleep(30)  # 30 seconds
    
    def _check_hedge_position(self, position_id: str):
        """
        Check if a position needs hedging.
        
        Args:
            position_id: Position ID to check
        """
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        
        if position.get("status") == "closed":
            return
        
        asset = position.get("asset")
        entry_price = position.get("entry_price", 0)
        current_price = self._get_current_price(asset)
        
        if not current_price or not entry_price:
            return
        
        position_size = position.get("size", 0)
        position_direction = 1 if position_size > 0 else -1
        
        if position_direction > 0:
            drawdown = (entry_price - current_price) / entry_price
        else:
            drawdown = (current_price - entry_price) / entry_price
        
        if drawdown > self.hedge_threshold:
            self._create_hedge(position_id)
    
    def _get_current_price(self, asset: str) -> Optional[float]:
        """
        Get current price for an asset.
        
        Args:
            asset: Asset symbol
            
        Returns:
            float: Current price, or None if not available
        """
        if asset in self.market_data:
            return self.market_data[asset].get("price")
        
        return None
    
    def _create_hedge(self, position_id: str):
        """
        Create a hedge for a position.
        
        Args:
            position_id: Position ID to hedge
        """
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        asset = position.get("asset")
        
        if asset not in self.market_data:
            return
        
        strategy_name = position.get("hedge_strategy", self.default_strategy)
        if strategy_name not in self.strategies:
            strategy_name = self.default_strategy
        
        strategy = self.strategies[strategy_name]
        
        hedge_params = strategy.calculate_hedge(position, self.market_data[asset])
        
        if not hedge_params:
            return
        
        hedge = HedgePosition(
            position_id=position_id,
            asset=asset,
            hedge_type=hedge_params["hedge_type"],
            size=hedge_params["size"],
            entry_price=hedge_params["price"],
            expiry=hedge_params.get("expiry"),
            metadata=hedge_params.get("metadata", {})
        )
        
        self.hedges[hedge.id] = hedge
        
        if self.visible_interface:
            logger.info(f"Created hedge: {hedge.hedge_type} for {asset} (size: {hedge.size}, price: {hedge.entry_price})")
        else:
            logger.debug(f"Created hedge: {hedge.hedge_type} for {asset} (size: {hedge.size}, price: {hedge.entry_price})")
        
        for callback in self._hedge_callbacks:
            try:
                callback(hedge)
            except Exception as e:
                logger.error(f"Error in hedge callback: {str(e)}")
    
    def close_hedge(self, hedge_id: str, exit_price: Optional[float] = None):
        """
        Close a hedge position.
        
        Args:
            hedge_id: Hedge ID to close
            exit_price: Exit price, or None to use current market price
        """
        if hedge_id not in self.hedges:
            logger.warning(f"Hedge {hedge_id} not found")
            return
        
        hedge = self.hedges[hedge_id]
        
        if hedge.status == "closed":
            return
        
        if exit_price is None:
            exit_price = self._get_current_price(hedge.asset)
            
            if not exit_price:
                logger.warning(f"No price available for {hedge.asset}, using entry price")
                exit_price = hedge.entry_price
        
        hedge.close(exit_price)
        
        if self.visible_interface:
            logger.info(f"Closed hedge: {hedge.hedge_type} for {hedge.asset} (PnL: {hedge.pnl:.2f})")
        else:
            logger.debug(f"Closed hedge: {hedge.hedge_type} for {hedge.asset} (PnL: {hedge.pnl:.2f})")
        
        for callback in self._hedge_callbacks:
            try:
                callback(hedge)
            except Exception as e:
                logger.error(f"Error in hedge callback: {str(e)}")
    
    def close_position_hedges(self, position_id: str, exit_price: Optional[float] = None):
        """
        Close all hedges for a position.
        
        Args:
            position_id: Position ID
            exit_price: Exit price, or None to use current market price
        """
        position_hedges = [
            hedge_id for hedge_id, hedge in self.hedges.items()
            if hedge.position_id == position_id and hedge.status == "active"
        ]
        
        for hedge_id in position_hedges:
            self.close_hedge(hedge_id, exit_price)
    
    def get_active_hedges(self) -> List[Dict[str, Any]]:
        """
        Get active hedge positions.
        
        Returns:
            List[Dict]: List of active hedges
        """
        return [
            hedge.to_dict() for hedge in self.hedges.values()
            if hedge.status == "active"
        ]
    
    def get_position_hedges(self, position_id: str) -> List[Dict[str, Any]]:
        """
        Get hedges for a specific position.
        
        Args:
            position_id: Position ID
            
        Returns:
            List[Dict]: List of hedges for the position
        """
        return [
            hedge.to_dict() for hedge in self.hedges.values()
            if hedge.position_id == position_id
        ]
    
    def get_hedge_stats(self) -> Dict[str, Any]:
        """
        Get statistics about hedge positions.
        
        Returns:
            Dict: Dictionary of hedge statistics
        """
        total_hedges = len(self.hedges)
        active_hedges = len([h for h in self.hedges.values() if h.status == "active"])
        closed_hedges = total_hedges - active_hedges
        
        total_pnl = sum([h.pnl for h in self.hedges.values() if h.status == "closed"])
        
        hedge_types = {}
        for hedge in self.hedges.values():
            if hedge.hedge_type not in hedge_types:
                hedge_types[hedge.hedge_type] = 0
            
            hedge_types[hedge.hedge_type] += 1
        
        return {
            "total_hedges": total_hedges,
            "active_hedges": active_hedges,
            "closed_hedges": closed_hedges,
            "total_pnl": total_pnl,
            "hedge_types": hedge_types
        }
    
    def stop_check(self):
        """
        Stop the background hedge check thread.
        """
        self._check_active = False
        
        if self.visible_interface:
            logger.info("Stopped auto hedging check thread")
        else:
            logger.debug("Stopped auto hedging check thread")


def create_auto_hedging(
    autonomous_mode: bool = True,
    visible_interface: bool = True,
    auto_hedge: bool = True
) -> AutoHedging:
    """
    Create a new auto hedging module.
    
    Args:
        autonomous_mode: Whether to operate in autonomous mode
        visible_interface: Whether to show detailed information in the interface
        auto_hedge: Whether to automatically hedge positions
        
    Returns:
        AutoHedging: New auto hedging module instance
    """
    return AutoHedging(
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface,
        auto_hedge=auto_hedge
    )
