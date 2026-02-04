"""
Interactive Brokers Connector using ib_insync.

Provides robust connection to Interactive Brokers TWS/Gateway
with automatic reconnection, heartbeat monitoring, rate limiting,
and circuit breaker protection.

Features:
- Paper trading support (port 7497)
- Automatic reconnection with exponential backoff
- IB error handling (502, 504, 1100)
- Rate limiting at 50 req/sec
- Circuit breaker for fault tolerance
- Structured JSON logging
- Latency tracking (p95 < 100ms target)
"""

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from contextlib import asynccontextmanager

from .base import (
    BaseConnector,
    ConnectorConfig,
    ConnectorState,
    ConnectionMetrics,
    setup_json_logger,
)
from .exceptions import (
    IBError,
    ConnectionError,
    ReconnectionError,
    DataConnectorError,
)
from .rate_limiter import RateLimiter
from .circuit_breaker import CircuitBreaker, CircuitState
from .heartbeat import HeartbeatMonitor


@dataclass
class IBConnectorConfig(ConnectorConfig):
    """
    Configuration specific to Interactive Brokers connector.
    
    Attributes:
        host: TWS/Gateway host (default: 127.0.0.1)
        port: TWS/Gateway port (7497 for paper, 7496 for live)
        client_id: Unique client ID for this connection
        readonly: If True, no orders can be placed
        account: Specific account to use (optional)
    """
    host: str = "127.0.0.1"
    port: int = 7497  # Paper trading port
    client_id: int = 1
    readonly: bool = False
    account: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "IBConnectorConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("IB_HOST", "127.0.0.1"),
            port=int(os.getenv("IB_PORT", "7497")),
            client_id=int(os.getenv("IB_CLIENT_ID", "1")),
            readonly=os.getenv("IB_READONLY", "false").lower() == "true",
            account=os.getenv("IB_ACCOUNT"),
            timeout=float(os.getenv("IB_TIMEOUT", "30.0")),
            max_reconnect_attempts=int(os.getenv("IB_MAX_RECONNECT", "5")),
            reconnect_delay=float(os.getenv("IB_RECONNECT_DELAY", "1.0")),
            heartbeat_interval=float(os.getenv("IB_HEARTBEAT_INTERVAL", "10.0")),
            rate_limit=int(os.getenv("IB_RATE_LIMIT", "50")),
        )


class IBConnector(BaseConnector):
    """
    Interactive Brokers connector with full resilience patterns.
    
    This connector provides robust connectivity to IB TWS/Gateway
    with automatic reconnection, rate limiting, circuit breaker,
    and heartbeat monitoring.
    
    Example:
        config = IBConnectorConfig(port=7497, client_id=1)
        connector = IBConnector(config)
        
        async with connector:
            # Get account info
            account = await connector.get_account_summary()
            
            # Get market data
            ticker = await connector.get_ticker("AAPL")
            
            # Place order
            order = await connector.place_order(
                symbol="AAPL",
                action="BUY",
                quantity=100,
                order_type="MKT"
            )
    
    IB Error Handling:
        - 502: Couldn't connect to TWS - triggers reconnection
        - 504: Not connected - triggers reconnection
        - 1100: Connectivity lost - triggers reconnection
    """
    
    # IB error codes that should trigger reconnection
    RECONNECT_ERROR_CODES = {502, 504, 1100, 1101, 2103, 2105, 2110}
    
    # IB error codes that are informational only
    INFO_ERROR_CODES = {1102, 2104, 2106}
    
    def __init__(
        self,
        config: Optional[IBConnectorConfig] = None,
        ib_client: Optional[Any] = None
    ):
        """
        Initialize IB connector.
        
        Args:
            config: Connector configuration
            ib_client: Optional pre-configured IB client (for testing)
        """
        self._ib_config = config or IBConnectorConfig()
        super().__init__(self._ib_config)
        
        self._ib = ib_client  # Will be set on connect if not provided
        self._account: Optional[str] = self._ib_config.account
        
        # Initialize resilience components
        self._rate_limiter = RateLimiter(
            rate=self._ib_config.rate_limit,
            burst=self._ib_config.rate_limit
        )
        
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self._ib_config.circuit_breaker_threshold,
            timeout=self._ib_config.circuit_breaker_timeout,
            name="ib_connector"
        )
        
        self._heartbeat_monitor: Optional[HeartbeatMonitor] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        
        # Request tracking
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._next_req_id = 1
        
        self._logger = setup_json_logger("IBConnector")
    
    def _get_next_req_id(self) -> int:
        """Get next request ID."""
        req_id = self._next_req_id
        self._next_req_id += 1
        return req_id
    
    async def connect(self) -> bool:
        """
        Connect to Interactive Brokers TWS/Gateway.
        
        Returns:
            True if connection successful
            
        Raises:
            ConnectionError: If connection fails
        """
        if self.is_connected:
            return True
        
        self.state = ConnectorState.CONNECTING
        
        try:
            # Import ib_insync here to allow graceful degradation
            try:
                from ib_insync import IB
            except ImportError:
                self._logger.warning(
                    "ib_insync not installed, using mock client"
                )
                self._ib = MockIBClient()
                return await self._complete_connection()
            
            if self._ib is None:
                self._ib = IB()
            
            # Set up error handler
            self._ib.errorEvent += self._on_ib_error
            self._ib.disconnectedEvent += self._on_disconnected
            
            # Connect with timeout
            self._logger.info(
                f"Connecting to IB at {self._ib_config.host}:{self._ib_config.port}",
                extra={"extra_data": self._ib_config.to_dict()}
            )
            
            await asyncio.wait_for(
                self._ib.connectAsync(
                    host=self._ib_config.host,
                    port=self._ib_config.port,
                    clientId=self._ib_config.client_id,
                    readonly=self._ib_config.readonly,
                ),
                timeout=self._ib_config.timeout
            )
            
            return await self._complete_connection()
            
        except asyncio.TimeoutError:
            self.state = ConnectorState.ERROR
            error = ConnectionError(
                message=f"Connection timeout after {self._ib_config.timeout}s",
                error_code=504
            )
            self._notify_error(error)
            raise error
            
        except Exception as e:
            self.state = ConnectorState.ERROR
            error = ConnectionError(
                message=f"Failed to connect: {e}",
                details={"original_error": str(e)}
            )
            self._notify_error(error)
            raise error
    
    async def _complete_connection(self) -> bool:
        """Complete connection setup after successful connect."""
        self.state = ConnectorState.CONNECTED
        self._metrics.connect_time = datetime.utcnow()
        
        # Mark mock client as connected if using mock
        if isinstance(self._ib, MockIBClient):
            self._ib._connected = True
        
        # Get account if not specified
        if self._account is None and hasattr(self._ib, 'managedAccounts'):
            accounts = self._ib.managedAccounts()
            if accounts:
                self._account = accounts[0]
        
        # Start heartbeat monitor
        self._heartbeat_monitor = HeartbeatMonitor(
            health_check=self.health_check,
            on_connection_lost=self._on_connection_lost,
            on_connection_restored=self._on_connection_restored,
            interval=self._ib_config.heartbeat_interval,
            timeout=self._ib_config.timeout,
        )
        await self._heartbeat_monitor.start()
        
        self._logger.info(
            "Connected to IB",
            extra={"extra_data": {
                "account": self._account,
                "client_id": self._ib_config.client_id
            }}
        )
        
        return True
    
    async def disconnect(self) -> None:
        """Disconnect from Interactive Brokers."""
        if self._heartbeat_monitor:
            await self._heartbeat_monitor.stop()
            self._heartbeat_monitor = None
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        
        if self._ib and hasattr(self._ib, 'disconnect'):
            self._ib.disconnect()
        
        self._metrics.disconnect_time = datetime.utcnow()
        self.state = ConnectorState.DISCONNECTED
        
        self._logger.info("Disconnected from IB")
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to Interactive Brokers.
        
        Uses exponential backoff with jitter for reconnection attempts.
        
        Returns:
            True if reconnection successful
            
        Raises:
            ReconnectionError: If all reconnection attempts fail
        """
        if self.state == ConnectorState.RECONNECTING:
            return False
        
        self.state = ConnectorState.RECONNECTING
        self._reconnect_count += 1
        self._metrics.reconnect_count += 1
        
        last_error: Optional[Exception] = None
        
        for attempt in range(1, self._ib_config.max_reconnect_attempts + 1):
            try:
                # Calculate delay with exponential backoff and jitter
                delay = min(
                    self._ib_config.reconnect_delay * (2 ** (attempt - 1)),
                    self._ib_config.reconnect_delay_max
                )
                # Add jitter (±20%)
                import random
                delay *= (0.8 + random.random() * 0.4)
                
                self._logger.info(
                    f"Reconnection attempt {attempt}/{self._ib_config.max_reconnect_attempts}",
                    extra={"extra_data": {
                        "attempt": attempt,
                        "delay": delay,
                        "total_reconnects": self._reconnect_count
                    }}
                )
                
                await asyncio.sleep(delay)
                
                # Disconnect first if needed
                if self._ib and hasattr(self._ib, 'isConnected') and self._ib.isConnected():
                    self._ib.disconnect()
                
                # Attempt reconnection
                await self.connect()
                
                if self.is_connected:
                    self._logger.info(
                        f"Reconnection successful after {attempt} attempts"
                    )
                    return True
                    
            except Exception as e:
                last_error = e
                self._logger.warning(
                    f"Reconnection attempt {attempt} failed: {e}"
                )
        
        # All attempts failed
        self.state = ConnectorState.ERROR
        error = ReconnectionError(
            message=f"Failed to reconnect after {self._ib_config.max_reconnect_attempts} attempts",
            attempts=self._ib_config.max_reconnect_attempts,
            last_error=last_error
        )
        self._notify_error(error)
        raise error
    
    async def health_check(self) -> bool:
        """
        Check connection health.
        
        Returns:
            True if connection is healthy
        """
        if not self._ib:
            return False
        
        try:
            if hasattr(self._ib, 'isConnected'):
                return self._ib.isConnected()
            # For mock client
            return getattr(self._ib, '_connected', False)
        except Exception:
            return False
    
    def _on_ib_error(self, req_id: int, error_code: int, error_string: str, contract: Any = None) -> None:
        """Handle IB error callback."""
        ib_error = IBError.from_ib_error(req_id, error_code, error_string)
        
        # Log based on severity
        if error_code in self.INFO_ERROR_CODES:
            self._logger.info(
                f"IB Info: {error_string}",
                extra={"extra_data": ib_error.to_dict()}
            )
        elif ib_error.is_recoverable:
            self._logger.warning(
                f"IB Recoverable Error: {error_string}",
                extra={"extra_data": ib_error.to_dict()}
            )
            # Trigger reconnection for recoverable errors
            if error_code in self.RECONNECT_ERROR_CODES:
                asyncio.create_task(self._trigger_reconnect())
        elif ib_error.is_fatal:
            self._logger.error(
                f"IB Fatal Error: {error_string}",
                extra={"extra_data": ib_error.to_dict()}
            )
            self._circuit_breaker.record_failure()
        else:
            self._logger.warning(
                f"IB Error: {error_string}",
                extra={"extra_data": ib_error.to_dict()}
            )
        
        # Notify error callbacks
        self._notify_error(ib_error)
        
        # Complete pending request with error if applicable
        if req_id in self._pending_requests:
            future = self._pending_requests.pop(req_id)
            if not future.done():
                future.set_exception(ib_error)
    
    def _on_disconnected(self) -> None:
        """Handle disconnection event."""
        self._logger.warning("Disconnected from IB")
        self.state = ConnectorState.DISCONNECTED
        asyncio.create_task(self._trigger_reconnect())
    
    async def _trigger_reconnect(self) -> None:
        """Trigger reconnection if not already in progress."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        self._reconnect_task = asyncio.create_task(self._reconnect_with_circuit_breaker())
    
    async def _reconnect_with_circuit_breaker(self) -> None:
        """Reconnect with circuit breaker protection."""
        if self._circuit_breaker.is_open:
            self._logger.warning("Circuit breaker is open, skipping reconnection")
            return
        
        try:
            await self.reconnect()
            self._circuit_breaker.record_success()
        except Exception as e:
            self._circuit_breaker.record_failure()
            self._logger.error(f"Reconnection failed: {e}")
    
    async def _on_connection_lost(self) -> None:
        """Handle connection lost from heartbeat monitor."""
        self._logger.error("Connection lost detected by heartbeat monitor")
        await self._trigger_reconnect()
    
    async def _on_connection_restored(self) -> None:
        """Handle connection restored from heartbeat monitor."""
        self._logger.info("Connection restored")
    
    @asynccontextmanager
    async def _rate_limited_request(self):
        """Context manager for rate-limited requests."""
        start_time = time.monotonic()
        
        await self._rate_limiter.acquire()
        
        try:
            yield
        finally:
            latency_ms = (time.monotonic() - start_time) * 1000
            self._metrics.record_latency(latency_ms)
            self._metrics.total_requests += 1
            
            # Log if latency exceeds target
            if latency_ms > 100:  # p95 target is 100ms
                self._logger.warning(
                    f"Request latency exceeded target: {latency_ms:.2f}ms",
                    extra={"extra_data": {"latency_ms": latency_ms}}
                )
    
    async def _execute_request(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute a request with all resilience patterns.
        
        Args:
            operation: The operation to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of the operation
        """
        async with self._rate_limited_request():
            return await self._circuit_breaker.execute(operation, *args, **kwargs)
    
    # ==================== Market Data Methods ====================
    
    async def get_ticker(self, symbol: str, exchange: str = "SMART") -> Dict[str, Any]:
        """
        Get current ticker data for a symbol.
        
        Args:
            symbol: The trading symbol
            exchange: Exchange to use (default: SMART)
            
        Returns:
            Dictionary with ticker data
        """
        async def _get_ticker():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'reqTickers'):
                # Real IB client
                from ib_insync import Stock
                contract = Stock(symbol, exchange, 'USD')
                self._ib.qualifyContracts(contract)
                ticker = self._ib.reqTickers(contract)[0]
                return {
                    "symbol": symbol,
                    "bid": ticker.bid,
                    "ask": ticker.ask,
                    "last": ticker.last,
                    "volume": ticker.volume,
                    "time": ticker.time.isoformat() if ticker.time else None,
                }
            else:
                # Mock client
                return await self._ib.get_ticker(symbol)
        
        return await self._execute_request(_get_ticker)
    
    async def get_historical_data(
        self,
        symbol: str,
        duration: str = "1 D",
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        exchange: str = "SMART"
    ) -> List[Dict[str, Any]]:
        """
        Get historical bar data.
        
        Args:
            symbol: The trading symbol
            duration: Duration string (e.g., "1 D", "1 W", "1 M")
            bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour")
            what_to_show: Data type (TRADES, MIDPOINT, BID, ASK)
            exchange: Exchange to use
            
        Returns:
            List of bar dictionaries
        """
        async def _get_historical():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'reqHistoricalData'):
                from ib_insync import Stock
                contract = Stock(symbol, exchange, 'USD')
                self._ib.qualifyContracts(contract)
                bars = self._ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow=what_to_show,
                    useRTH=True,
                )
                return [
                    {
                        "date": bar.date.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ]
            else:
                return await self._ib.get_historical_data(symbol, duration, bar_size)
        
        return await self._execute_request(_get_historical)
    
    # ==================== Account Methods ====================
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get account summary.
        
        Returns:
            Dictionary with account information
        """
        async def _get_account():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'accountSummary'):
                summary = self._ib.accountSummary(self._account)
                return {
                    item.tag: item.value
                    for item in summary
                }
            else:
                return await self._ib.get_account_summary()
        
        return await self._execute_request(_get_account)
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Returns:
            List of position dictionaries
        """
        async def _get_positions():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'positions'):
                positions = self._ib.positions(self._account)
                return [
                    {
                        "symbol": pos.contract.symbol,
                        "position": pos.position,
                        "avg_cost": pos.avgCost,
                        "market_value": pos.marketValue if hasattr(pos, 'marketValue') else None,
                    }
                    for pos in positions
                ]
            else:
                return await self._ib.get_positions()
        
        return await self._execute_request(_get_positions)
    
    # ==================== Order Methods ====================
    
    async def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MKT",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        exchange: str = "SMART"
    ) -> Dict[str, Any]:
        """
        Place an order.
        
        Args:
            symbol: Trading symbol
            action: BUY or SELL
            quantity: Number of shares/contracts
            order_type: MKT, LMT, STP, STP_LMT
            limit_price: Limit price (for LMT orders)
            stop_price: Stop price (for STP orders)
            exchange: Exchange to use
            
        Returns:
            Order confirmation dictionary
        """
        async def _place_order():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if self._ib_config.readonly:
                raise DataConnectorError("Cannot place orders in readonly mode")
            
            if hasattr(self._ib, 'placeOrder'):
                from ib_insync import Stock, MarketOrder, LimitOrder, StopOrder
                
                contract = Stock(symbol, exchange, 'USD')
                self._ib.qualifyContracts(contract)
                
                if order_type == "MKT":
                    order = MarketOrder(action, quantity)
                elif order_type == "LMT":
                    order = LimitOrder(action, quantity, limit_price)
                elif order_type == "STP":
                    order = StopOrder(action, quantity, stop_price)
                else:
                    raise ValueError(f"Unsupported order type: {order_type}")
                
                trade = self._ib.placeOrder(contract, order)
                return {
                    "order_id": trade.order.orderId,
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "order_type": order_type,
                    "status": trade.orderStatus.status,
                }
            else:
                return await self._ib.place_order(
                    symbol, action, quantity, order_type, limit_price, stop_price
                )
        
        return await self._execute_request(_place_order)
    
    async def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: The order ID to cancel
            
        Returns:
            True if cancellation request sent
        """
        async def _cancel_order():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'cancelOrder'):
                order = self._ib.orders().get(order_id)
                if order:
                    self._ib.cancelOrder(order)
                    return True
                return False
            else:
                return await self._ib.cancel_order(order_id)
        
        return await self._execute_request(_cancel_order)
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders.
        
        Returns:
            List of open order dictionaries
        """
        async def _get_orders():
            if not self.is_connected:
                raise ConnectionError("Not connected to IB")
            
            if hasattr(self._ib, 'openOrders'):
                orders = self._ib.openOrders()
                return [
                    {
                        "order_id": order.orderId,
                        "symbol": order.contract.symbol if order.contract else None,
                        "action": order.action,
                        "quantity": order.totalQuantity,
                        "order_type": order.orderType,
                        "status": order.status,
                    }
                    for order in orders
                ]
            else:
                return await self._ib.get_open_orders()
        
        return await self._execute_request(_get_orders)
    
    # ==================== Metrics and Status ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive connector status."""
        return {
            "state": self.state.value,
            "is_connected": self.is_connected,
            "account": self._account,
            "config": self._ib_config.to_dict(),
            "metrics": self._metrics.to_dict(),
            "rate_limiter": self._rate_limiter.get_metrics(),
            "circuit_breaker": self._circuit_breaker.get_metrics(),
            "heartbeat": self._heartbeat_monitor.get_metrics() if self._heartbeat_monitor else None,
        }


class MockIBClient:
    """
    Mock IB client for testing without TWS/Gateway.
    
    Provides simulated responses for all IB operations.
    """
    
    def __init__(self):
        self._connected = False
        self._orders: Dict[int, Dict] = {}
        self._next_order_id = 1
    
    async def connect(self) -> None:
        """Simulate connection."""
        await asyncio.sleep(0.1)
        self._connected = True
    
    def disconnect(self) -> None:
        """Simulate disconnection."""
        self._connected = False
    
    def isConnected(self) -> bool:
        """Check connection status."""
        return self._connected
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get mock ticker data."""
        import random
        base_price = 150.0 if symbol == "AAPL" else 100.0
        return {
            "symbol": symbol,
            "bid": base_price - 0.01,
            "ask": base_price + 0.01,
            "last": base_price,
            "volume": random.randint(1000000, 5000000),
            "time": datetime.utcnow().isoformat(),
        }
    
    async def get_historical_data(
        self,
        symbol: str,
        duration: str,
        bar_size: str
    ) -> List[Dict[str, Any]]:
        """Get mock historical data."""
        import random
        bars = []
        base_price = 150.0 if symbol == "AAPL" else 100.0
        
        for i in range(100):
            price = base_price + random.uniform(-5, 5)
            bars.append({
                "date": datetime.utcnow().isoformat(),
                "open": price,
                "high": price + random.uniform(0, 1),
                "low": price - random.uniform(0, 1),
                "close": price + random.uniform(-0.5, 0.5),
                "volume": random.randint(10000, 100000),
            })
        
        return bars
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """Get mock account summary."""
        return {
            "NetLiquidation": "100000.00",
            "TotalCashValue": "50000.00",
            "BuyingPower": "200000.00",
            "GrossPositionValue": "50000.00",
        }
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get mock positions."""
        return [
            {
                "symbol": "AAPL",
                "position": 100,
                "avg_cost": 145.50,
                "market_value": 15000.00,
            }
        ]
    
    async def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[float],
        stop_price: Optional[float]
    ) -> Dict[str, Any]:
        """Place mock order."""
        order_id = self._next_order_id
        self._next_order_id += 1
        
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "order_type": order_type,
            "status": "Submitted",
        }
        self._orders[order_id] = order
        return order
    
    async def cancel_order(self, order_id: int) -> bool:
        """Cancel mock order."""
        if order_id in self._orders:
            self._orders[order_id]["status"] = "Cancelled"
            return True
        return False
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get mock open orders."""
        return [
            order for order in self._orders.values()
            if order["status"] not in ("Filled", "Cancelled")
        ]
