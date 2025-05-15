"""
Cross-Chain Arbitrage Module for AUTOBOT

This module provides functionality for identifying and executing arbitrage
opportunities across different blockchains and exchanges. It monitors price
differences for the same asset across multiple chains and executes trades
when profitable opportunities are detected.
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from collections import deque

from autobot.thread_management import (
    create_managed_thread,
    is_shutdown_requested,
    ManagedThread
)

logger = logging.getLogger(__name__)

class ArbitrageOpportunity:
    """Represents a cross-chain arbitrage opportunity"""
    
    def __init__(
        self,
        asset: str,
        source_chain: str,
        target_chain: str,
        source_price: float,
        target_price: float,
        price_difference: float,
        profit_percentage: float,
        timestamp: Optional[float] = None,
        estimated_fees: Optional[Dict[str, float]] = None
    ):
        """
        Initialize an arbitrage opportunity.
        
        Args:
            asset: Asset symbol (e.g., "ETH")
            source_chain: Source blockchain/exchange
            target_chain: Target blockchain/exchange
            source_price: Price on source chain
            target_price: Price on target chain
            price_difference: Absolute price difference
            profit_percentage: Profit percentage after fees
            timestamp: Opportunity timestamp
            estimated_fees: Estimated fees for executing the arbitrage
        """
        self.asset = asset
        self.source_chain = source_chain
        self.target_chain = target_chain
        self.source_price = source_price
        self.target_price = target_price
        self.price_difference = price_difference
        self.profit_percentage = profit_percentage
        self.timestamp = timestamp or datetime.now().timestamp()
        self.estimated_fees = estimated_fees or {}
        self.id = f"{asset}_{source_chain}_{target_chain}_{int(self.timestamp)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert opportunity to dictionary"""
        return {
            "id": self.id,
            "asset": self.asset,
            "source_chain": self.source_chain,
            "target_chain": self.target_chain,
            "source_price": self.source_price,
            "target_price": self.target_price,
            "price_difference": self.price_difference,
            "profit_percentage": self.profit_percentage,
            "timestamp": self.timestamp,
            "estimated_fees": self.estimated_fees
        }


class CrossChainArbitrage:
    """
    Cross-chain arbitrage module for identifying and executing arbitrage
    opportunities across different blockchains and exchanges.
    """
    
    def __init__(
        self,
        autonomous_mode: bool = True,
        visible_interface: bool = True,
        scan_interval: int = 10,  # 10 seconds
        min_profit_threshold: float = 0.5,  # 0.5% minimum profit
        max_position_size: float = 1000.0,  # $1000 max position size
        max_concurrent_trades: int = 3,
        execution_timeout: int = 300  # 5 minutes
    ):
        """
        Initialize the cross-chain arbitrage module.
        
        Args:
            autonomous_mode: Whether to operate in autonomous mode
            visible_interface: Whether to show detailed information in the interface
            scan_interval: Interval between opportunity scans (in seconds)
            min_profit_threshold: Minimum profit percentage to execute arbitrage
            max_position_size: Maximum position size per arbitrage
            max_concurrent_trades: Maximum number of concurrent arbitrage trades
            execution_timeout: Timeout for arbitrage execution (in seconds)
        """
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.scan_interval = scan_interval
        self.min_profit_threshold = min_profit_threshold
        self.max_position_size = max_position_size
        self.max_concurrent_trades = max_concurrent_trades
        self.execution_timeout = execution_timeout
        
        self.price_data = {}  # {asset: {chain: price}}
        self.fee_data = {}  # {chain: {type: fee}}
        self.bridge_times = {}  # {source_chain: {target_chain: seconds}}
        
        self.detected_opportunities = []
        self.active_arbitrages = {}
        self.completed_arbitrages = []
        
        self._opportunity_callbacks = []
        self._scanning_thread = None
        self._scanning_active = False
        self._execution_threads = {}
        
        # if self.autonomous_mode:
        #     self._start_scanning_thread()
    
    def update_price(self, asset: str, chain: str, price: float):
        """
        Update price data for an asset on a specific chain.
        
        Args:
            asset: Asset symbol
            chain: Blockchain/exchange name
            price: Current price
        """
        if asset not in self.price_data:
            self.price_data[asset] = {}
        
        self.price_data[asset][chain] = {
            "price": price,
            "timestamp": datetime.now().timestamp()
        }
    
    def update_fee(self, chain: str, fee_type: str, fee: float):
        """
        Update fee data for a chain.
        
        Args:
            chain: Blockchain/exchange name
            fee_type: Fee type (e.g., "gas", "bridge", "trading")
            fee: Fee amount
        """
        if chain not in self.fee_data:
            self.fee_data[chain] = {}
        
        self.fee_data[chain][fee_type] = {
            "fee": fee,
            "timestamp": datetime.now().timestamp()
        }
    
    def update_bridge_time(self, source_chain: str, target_chain: str, seconds: int):
        """
        Update estimated bridge time between chains.
        
        Args:
            source_chain: Source blockchain
            target_chain: Target blockchain
            seconds: Estimated bridge time in seconds
        """
        if source_chain not in self.bridge_times:
            self.bridge_times[source_chain] = {}
        
        self.bridge_times[source_chain][target_chain] = {
            "seconds": seconds,
            "timestamp": datetime.now().timestamp()
        }
    
    def register_opportunity_callback(self, callback):
        """
        Register a callback to be called when an arbitrage opportunity is detected.
        
        Args:
            callback: Function to call when an opportunity is detected
        """
        self._opportunity_callbacks.append(callback)
    
    def _start_scanning_thread(self):
        """
        Start the background scanning thread.
        """
        if self._scanning_thread is not None and self._scanning_thread.is_alive():
            return
        
        self._scanning_active = True
        self._scanning_thread = create_managed_thread(
            name="cross_chain_arbitrage_scanner",
            target=self._scanning_loop,
            daemon=True,
            auto_start=True,
            cleanup_callback=lambda: setattr(self, '_scanning_active', False)
        )
        
        if self.visible_interface:
            logger.info("Started cross-chain arbitrage scanning thread")
        else:
            logger.debug("Started cross-chain arbitrage scanning thread")
    
    def _scanning_loop(self):
        """
        Background loop for continuous arbitrage opportunity scanning.
        """
        while self._scanning_active and not is_shutdown_requested():
            try:
                self._scan_opportunities()
                
                for _ in range(min(10, self.scan_interval)):
                    if not self._scanning_active or is_shutdown_requested():
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in arbitrage scanning loop: {str(e)}")
                
                for _ in range(15):  # 15 * 2s = 30 seconds
                    if not self._scanning_active or is_shutdown_requested():
                        break
                    time.sleep(2)
    
    def _scan_opportunities(self):
        """
        Scan for arbitrage opportunities across all assets and chains.
        """
        current_time = datetime.now().timestamp()
        
        for asset, chains in self.price_data.items():
            if len(chains) < 2:
                continue
            
            recent_chains = {
                chain: data["price"]
                for chain, data in chains.items()
                if current_time - data["timestamp"] < 300  # 5 minutes
            }
            
            if len(recent_chains) < 2:
                continue
            
            chain_names = list(recent_chains.keys())
            for i in range(len(chain_names)):
                for j in range(i + 1, len(chain_names)):
                    source_chain = chain_names[i]
                    target_chain = chain_names[j]
                    
                    source_price = recent_chains[source_chain]
                    target_price = recent_chains[target_chain]
                    
                    if abs(source_price - target_price) / min(source_price, target_price) < 0.001:
                        continue
                    
                    if source_price < target_price:
                        buy_chain = source_chain
                        sell_chain = target_chain
                        buy_price = source_price
                        sell_price = target_price
                    else:
                        buy_chain = target_chain
                        sell_chain = source_chain
                        buy_price = target_price
                        sell_price = source_price
                    
                    price_difference = sell_price - buy_price
                    price_difference_percentage = price_difference / buy_price * 100
                    
                    estimated_fees = self._estimate_fees(asset, buy_chain, sell_chain)
                    total_fee_percentage = sum(estimated_fees.values())
                    
                    profit_percentage = price_difference_percentage - total_fee_percentage
                    
                    if profit_percentage > self.min_profit_threshold:
                        opportunity = ArbitrageOpportunity(
                            asset=asset,
                            source_chain=buy_chain,
                            target_chain=sell_chain,
                            source_price=buy_price,
                            target_price=sell_price,
                            price_difference=price_difference,
                            profit_percentage=profit_percentage,
                            timestamp=current_time,
                            estimated_fees=estimated_fees
                        )
                        
                        self._process_opportunity(opportunity)
    
    def _estimate_fees(self, asset: str, source_chain: str, target_chain: str) -> Dict[str, float]:
        """
        Estimate fees for an arbitrage between chains.
        
        Args:
            asset: Asset symbol
            source_chain: Source blockchain/exchange
            target_chain: Target blockchain/exchange
            
        Returns:
            Dict: Dictionary of fee types and percentages
        """
        fees = {}
        
        source_trading_fee = 0.1  # Default 0.1%
        if source_chain in self.fee_data and "trading" in self.fee_data[source_chain]:
            source_trading_fee = self.fee_data[source_chain]["trading"]["fee"]
        
        target_trading_fee = 0.1  # Default 0.1%
        if target_chain in self.fee_data and "trading" in self.fee_data[target_chain]:
            target_trading_fee = self.fee_data[target_chain]["trading"]["fee"]
        
        fees["source_trading"] = source_trading_fee
        fees["target_trading"] = target_trading_fee
        
        if source_chain != target_chain:
            bridge_fee = 0.3  # Default 0.3%
            
            if source_chain in self.fee_data and "bridge" in self.fee_data[source_chain]:
                bridge_fee = self.fee_data[source_chain]["bridge"]["fee"]
            
            fees["bridge"] = bridge_fee
        
        source_gas_fee = 0.05  # Default 0.05%
        if source_chain in self.fee_data and "gas" in self.fee_data[source_chain]:
            source_gas_fee = self.fee_data[source_chain]["gas"]["fee"]
        
        target_gas_fee = 0.05  # Default 0.05%
        if target_chain in self.fee_data and "gas" in self.fee_data[target_chain]:
            target_gas_fee = self.fee_data[target_chain]["gas"]["fee"]
        
        fees["source_gas"] = source_gas_fee
        fees["target_gas"] = target_gas_fee
        
        fees["slippage"] = 0.2  # Default 0.2%
        
        return fees
    
    def _process_opportunity(self, opportunity: ArbitrageOpportunity):
        """
        Process a detected arbitrage opportunity.
        
        Args:
            opportunity: Arbitrage opportunity
        """
        self.detected_opportunities.append(opportunity)
        
        if self.visible_interface:
            logger.info(f"Arbitrage opportunity: {opportunity.asset} from {opportunity.source_chain} to {opportunity.target_chain} ({opportunity.profit_percentage:.2f}% profit)")
        else:
            logger.debug(f"Arbitrage opportunity: {opportunity.asset} from {opportunity.source_chain} to {opportunity.target_chain} ({opportunity.profit_percentage:.2f}% profit)")
        
        for callback in self._opportunity_callbacks:
            try:
                callback(opportunity)
            except Exception as e:
                logger.error(f"Error in arbitrage opportunity callback: {str(e)}")
        
        if self.autonomous_mode and len(self.active_arbitrages) < self.max_concurrent_trades:
            self._execute_arbitrage(opportunity)
    
    def _execute_arbitrage(self, opportunity: ArbitrageOpportunity):
        """
        Execute an arbitrage opportunity.
        
        Args:
            opportunity: Arbitrage opportunity
        """
        position_size = min(
            self.max_position_size,
            self.max_position_size * (opportunity.profit_percentage / 5.0)  # Scale by profit
        )
        
        self.active_arbitrages[opportunity.id] = {
            "opportunity": opportunity.to_dict(),
            "position_size": position_size,
            "status": "starting",
            "start_time": datetime.now().timestamp(),
            "steps": []
        }
        
        thread = create_managed_thread(
            name=f"arbitrage_execution_{opportunity.id}",
            target=self._arbitrage_execution_thread,
            args=(opportunity.id,),
            daemon=True,
            auto_start=True
        )
        self._execution_threads[opportunity.id] = thread
        
        if self.visible_interface:
            logger.info(f"Started arbitrage execution: {opportunity.asset} from {opportunity.source_chain} to {opportunity.target_chain} (${position_size:.2f})")
        else:
            logger.debug(f"Started arbitrage execution: {opportunity.asset} from {opportunity.source_chain} to {opportunity.target_chain} (${position_size:.2f})")
    
    def _arbitrage_execution_thread(self, opportunity_id: str):
        """
        Background thread for executing an arbitrage opportunity.
        
        Args:
            opportunity_id: ID of the opportunity to execute
        """
        try:
            if opportunity_id not in self.active_arbitrages or is_shutdown_requested():
                return
            
            arbitrage = self.active_arbitrages[opportunity_id]
            opportunity = arbitrage["opportunity"]
            position_size = arbitrage["position_size"]
            
            arbitrage["status"] = "executing"
            arbitrage["steps"].append({
                "step": "started",
                "timestamp": datetime.now().timestamp()
            })
            
            if is_shutdown_requested():
                return
                
            arbitrage["steps"].append({
                "step": "buying",
                "chain": opportunity["source_chain"],
                "price": opportunity["source_price"],
                "timestamp": datetime.now().timestamp()
            })
            
            for _ in range(20):  # 0.1s increments for 2s
                if is_shutdown_requested():
                    return
                time.sleep(0.1)
            
            if is_shutdown_requested():
                return
                
            buy_amount = position_size / opportunity["source_price"]
            
            if opportunity["source_chain"] != opportunity["target_chain"] and not is_shutdown_requested():
                arbitrage["steps"].append({
                    "step": "bridging",
                    "from_chain": opportunity["source_chain"],
                    "to_chain": opportunity["target_chain"],
                    "timestamp": datetime.now().timestamp()
                })
                
                bridge_time = 10  # Default 10 seconds
                if (opportunity["source_chain"] in self.bridge_times and 
                    opportunity["target_chain"] in self.bridge_times[opportunity["source_chain"]]):
                    bridge_time = self.bridge_times[opportunity["source_chain"]][opportunity["target_chain"]]["seconds"]
                
                bridge_time_seconds = min(bridge_time, 5)  # max 5 seconds for simulation
                for _ in range(int(bridge_time_seconds * 10)):  # 0.1s increments
                    if is_shutdown_requested():
                        return
                    time.sleep(0.1)
                
                if is_shutdown_requested():
                    return
                    
                bridge_fee = opportunity["estimated_fees"].get("bridge", 0.3) / 100
                buy_amount = buy_amount * (1 - bridge_fee)
            
            if is_shutdown_requested():
                return
                
            arbitrage["steps"].append({
                "step": "selling",
                "chain": opportunity["target_chain"],
                "price": opportunity["target_price"],
                "timestamp": datetime.now().timestamp()
            })
            
            for _ in range(20):  # 0.1s increments for 2s
                if is_shutdown_requested():
                    return
                time.sleep(0.1)
            
            if is_shutdown_requested():
                return
                
            target_trading_fee = opportunity["estimated_fees"].get("target_trading", 0.1) / 100
            sell_amount = buy_amount * opportunity["target_price"] * (1 - target_trading_fee)
            
            profit = sell_amount - position_size
            profit_percentage = (profit / position_size) * 100
            
            if is_shutdown_requested():
                return
                
            arbitrage["status"] = "completed"
            arbitrage["steps"].append({
                "step": "completed",
                "profit": profit,
                "profit_percentage": profit_percentage,
                "timestamp": datetime.now().timestamp()
            })
            
            if opportunity_id in self.active_arbitrages and not is_shutdown_requested():
                self.completed_arbitrages.append(arbitrage)
                del self.active_arbitrages[opportunity_id]
            
                if self.visible_interface:
                    logger.info(f"Completed arbitrage: {opportunity['asset']} from {opportunity['source_chain']} to {opportunity['target_chain']} (profit: ${profit:.2f}, {profit_percentage:.2f}%)")
                else:
                    logger.debug(f"Completed arbitrage: {opportunity['asset']} from {opportunity['source_chain']} to {opportunity['target_chain']} (profit: ${profit:.2f}, {profit_percentage:.2f}%)")
            
        except Exception as e:
            logger.error(f"Error executing arbitrage {opportunity_id}: {str(e)}")
            
            if opportunity_id in self.active_arbitrages and not is_shutdown_requested():
                self.active_arbitrages[opportunity_id]["status"] = "failed"
                self.active_arbitrages[opportunity_id]["steps"].append({
                    "step": "failed",
                    "error": str(e),
                    "timestamp": datetime.now().timestamp()
                })
                
                self.completed_arbitrages.append(self.active_arbitrages[opportunity_id])
                del self.active_arbitrages[opportunity_id]
    
    def get_active_arbitrages(self) -> List[Dict[str, Any]]:
        """
        Get active arbitrage executions.
        
        Returns:
            List[Dict]: List of active arbitrages
        """
        return list(self.active_arbitrages.values())
    
    def get_completed_arbitrages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get completed arbitrage executions.
        
        Args:
            limit: Maximum number of arbitrages to return
            
        Returns:
            List[Dict]: List of completed arbitrages
        """
        arbitrages = sorted(self.completed_arbitrages, key=lambda a: a["start_time"], reverse=True)
        
        if limit is not None:
            arbitrages = arbitrages[:limit]
        
        return arbitrages
    
    def get_arbitrage_stats(self) -> Dict[str, Any]:
        """
        Get statistics about arbitrage executions.
        
        Returns:
            Dict: Dictionary of arbitrage statistics
        """
        total_profit = 0.0
        total_volume = 0.0
        success_count = 0
        fail_count = 0
        
        for arbitrage in self.completed_arbitrages:
            if arbitrage["status"] == "completed":
                success_count += 1
                
                for step in reversed(arbitrage["steps"]):
                    if step["step"] == "completed":
                        total_profit += step.get("profit", 0)
                        break
                
                total_volume += arbitrage["position_size"]
            else:
                fail_count += 1
        
        return {
            "total_opportunities": len(self.detected_opportunities),
            "total_executions": len(self.completed_arbitrages),
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": success_count / max(1, len(self.completed_arbitrages)) * 100,
            "total_profit": total_profit,
            "total_volume": total_volume,
            "roi": total_profit / max(1, total_volume) * 100,
            "active_arbitrages": len(self.active_arbitrages)
        }
    
    def stop_scanning(self):
        """
        Stop the background scanning thread.
        """
        self._scanning_active = False
        
        if self.visible_interface:
            logger.info("Stopped cross-chain arbitrage scanning thread")
        else:
            logger.debug("Stopped cross-chain arbitrage scanning thread")


def create_cross_chain_arbitrage(
    autonomous_mode: bool = True,
    visible_interface: bool = True
) -> CrossChainArbitrage:
    """
    Create a new cross-chain arbitrage module.
    
    Args:
        autonomous_mode: Whether to operate in autonomous mode
        visible_interface: Whether to show detailed information in the interface
        
    Returns:
        CrossChainArbitrage: New arbitrage module instance
    """
    return CrossChainArbitrage(
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface
    )
