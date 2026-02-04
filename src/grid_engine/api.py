"""
API Endpoints for AUTOBOT Grid Trading Engine.

Provides REST API endpoints for:
- Grid configuration and status
- Order management
- Position tracking
- Risk monitoring
- Real-time WebSocket updates
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import yaml

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .grid_calculator import GridCalculator, GridConfig, GridLevel
from .order_manager import GridOrderManager, GridOrder, OrderStatus
from .position_tracker import PositionTracker, TradeType
from .rebalance import GridRebalancer, RebalanceReason
from .risk_manager import GridRiskManager, RiskLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grid", tags=["Grid Trading"])


# =============================================================================
# Pydantic Models for API
# =============================================================================

class GridConfigRequest(BaseModel):
    """Request model for grid configuration."""
    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    total_capital: float = Field(..., gt=0, description="Total capital to allocate")
    num_levels: int = Field(default=15, ge=5, le=50, description="Number of grid levels")
    range_percent: float = Field(default=14.0, gt=0, le=50, description="Total range percentage")
    profit_per_level: float = Field(default=0.8, gt=0, le=10, description="Target profit per level")
    center_price: float = Field(..., gt=0, description="Center price for grid")


class GridStatusResponse(BaseModel):
    """Response model for grid status."""
    symbol: str
    center_price: Optional[float]
    upper_bound: Optional[float]
    lower_bound: Optional[float]
    total_levels: int
    active_levels: int
    total_capital: float
    is_active: bool


class OrderResponse(BaseModel):
    """Response model for order information."""
    order_id: str
    level_id: int
    symbol: str
    side: str
    price: float
    quantity: float
    status: str
    filled_quantity: float
    created_at: str


class PositionResponse(BaseModel):
    """Response model for position information."""
    position_id: str
    level_id: int
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float


class RiskStatusResponse(BaseModel):
    """Response model for risk status."""
    level: str
    daily_pnl: float
    daily_loss_limit: float
    total_pnl: float
    total_pnl_percent: float
    max_drawdown: float
    is_trading_allowed: bool
    active_alerts: int


class MetricsResponse(BaseModel):
    """Response model for performance metrics."""
    symbol: str
    initial_capital: float
    current_equity: float
    total_pnl: float
    return_percent: float
    win_rate: float
    total_trades: int
    max_drawdown: float


class RebalanceRequest(BaseModel):
    """Request model for manual rebalance."""
    new_center_price: float = Field(..., gt=0, description="New center price")
    reason: str = Field(default="manual", description="Reason for rebalance")


class EmergencyStopRequest(BaseModel):
    """Request model for emergency stop."""
    reason: str = Field(default="Manual emergency stop", description="Reason for stop")


# =============================================================================
# Grid Engine State (Singleton for demo - use dependency injection in production)
# =============================================================================

class GridEngineState:
    """Manages the state of the grid trading engine."""
    
    _instance: Optional["GridEngineState"] = None
    
    def __init__(self):
        self.grid_calculator: Optional[GridCalculator] = None
        self.order_manager: Optional[GridOrderManager] = None
        self.position_tracker: Optional[PositionTracker] = None
        self.rebalancer: Optional[GridRebalancer] = None
        self.risk_manager: Optional[GridRiskManager] = None
        self.is_initialized: bool = False
        self.is_running: bool = False
        self._websocket_clients: List[WebSocket] = []
        self._price_update_task: Optional[asyncio.Task] = None
    
    @classmethod
    def get_instance(cls) -> "GridEngineState":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def initialize(
        self,
        symbol: str,
        total_capital: float,
        center_price: float,
        num_levels: int = 15,
        range_percent: float = 14.0,
        profit_per_level: float = 0.8,
        paper_trading: bool = True
    ) -> None:
        """Initialize the grid engine with configuration."""
        config = GridConfig(
            symbol=symbol,
            total_capital=total_capital,
            num_levels=num_levels,
            range_percent=range_percent,
            profit_per_level=profit_per_level,
        )
        
        self.grid_calculator = GridCalculator(config)
        self.grid_calculator.calculate_grid(center_price)
        
        self.order_manager = GridOrderManager(
            grid_calculator=self.grid_calculator,
            paper_trading=paper_trading
        )
        
        self.position_tracker = PositionTracker(
            symbol=symbol,
            initial_capital=total_capital
        )
        
        self.rebalancer = GridRebalancer(
            grid_calculator=self.grid_calculator,
            order_manager=self.order_manager,
            position_tracker=self.position_tracker
        )
        
        self.risk_manager = GridRiskManager(
            initial_capital=total_capital,
            position_tracker=self.position_tracker,
            order_manager=self.order_manager
        )
        
        self.is_initialized = True
        logger.info(f"Grid engine initialized for {symbol} with {total_capital}€")
    
    async def broadcast_update(self, update_type: str, data: Dict[str, Any]) -> None:
        """Broadcast update to all connected WebSocket clients."""
        message = {
            "type": update_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        
        disconnected = []
        for client in self._websocket_clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)
        
        for client in disconnected:
            self._websocket_clients.remove(client)


def get_engine_state() -> GridEngineState:
    """Dependency to get grid engine state."""
    return GridEngineState.get_instance()


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/initialize", response_model=GridStatusResponse)
async def initialize_grid(
    config: GridConfigRequest,
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Initialize the grid trading engine with configuration.
    
    This creates the grid levels and prepares the engine for trading.
    """
    try:
        state.initialize(
            symbol=config.symbol,
            total_capital=config.total_capital,
            center_price=config.center_price,
            num_levels=config.num_levels,
            range_percent=config.range_percent,
            profit_per_level=config.profit_per_level,
        )
        
        return GridStatusResponse(
            symbol=config.symbol,
            center_price=state.grid_calculator.center_price,
            upper_bound=state.grid_calculator.upper_bound,
            lower_bound=state.grid_calculator.lower_bound,
            total_levels=len(state.grid_calculator.levels),
            active_levels=0,
            total_capital=config.total_capital,
            is_active=False
        )
        
    except Exception as e:
        logger.error(f"Failed to initialize grid: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_grid_trading(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Start grid trading by placing initial orders.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    if state.is_running:
        raise HTTPException(status_code=400, detail="Grid already running")
    
    try:
        orders = await state.order_manager.initialize_grid_orders()
        state.is_running = True
        
        await state.broadcast_update("grid_started", {
            "orders_placed": len(orders),
            "symbol": state.grid_calculator.config.symbol
        })
        
        return {
            "status": "started",
            "orders_placed": len(orders),
            "message": f"Grid trading started with {len(orders)} orders"
        }
        
    except Exception as e:
        logger.error(f"Failed to start grid: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_grid_trading(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Stop grid trading by canceling all orders.
    """
    if not state.is_running:
        raise HTTPException(status_code=400, detail="Grid not running")
    
    try:
        canceled = await state.order_manager.cancel_all_orders()
        state.is_running = False
        
        await state.broadcast_update("grid_stopped", {
            "orders_canceled": canceled
        })
        
        return {
            "status": "stopped",
            "orders_canceled": canceled,
            "message": f"Grid trading stopped, {canceled} orders canceled"
        }
        
    except Exception as e:
        logger.error(f"Failed to stop grid: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_grid_status(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get current grid status including levels, orders, and positions.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return {
        "grid": state.grid_calculator.get_status(),
        "orders": state.order_manager.get_status(),
        "positions": state.position_tracker.get_position_summary(),
        "risk": state.risk_manager.get_status(),
        "is_running": state.is_running
    }


@router.get("/levels")
async def get_grid_levels(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get all grid levels with their current status.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return {
        "levels": [level.to_dict() for level in state.grid_calculator.levels],
        "total": len(state.grid_calculator.levels),
        "buy_levels": len(state.grid_calculator.buy_levels),
        "sell_levels": len(state.grid_calculator.sell_levels)
    }


@router.get("/orders")
async def get_orders(
    active_only: bool = Query(default=False, description="Return only active orders"),
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get all orders or only active orders.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    if active_only:
        orders = state.order_manager.active_orders
    else:
        orders = list(state.order_manager.orders.values())
    
    return {
        "orders": [o.to_dict() for o in orders],
        "total": len(orders)
    }


@router.get("/positions")
async def get_positions(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get all open positions.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return state.position_tracker.get_position_summary()


@router.get("/metrics")
async def get_metrics(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get performance metrics.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return state.position_tracker.get_metrics()


@router.get("/risk")
async def get_risk_status(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get current risk status and alerts.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return state.risk_manager.to_dict()


@router.post("/rebalance")
async def rebalance_grid(
    request: RebalanceRequest,
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Manually trigger grid rebalance with new center price.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    try:
        action = await state.rebalancer.execute_rebalance(
            new_center_price=request.new_center_price,
            reason=RebalanceReason.MANUAL_REBALANCE
        )
        
        await state.broadcast_update("rebalance_completed", action.to_dict())
        
        return action.to_dict()
        
    except Exception as e:
        logger.error(f"Rebalance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rebalance/recommendation")
async def get_rebalance_recommendation(
    current_price: float = Query(..., gt=0, description="Current market price"),
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get recommendation for whether to rebalance.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return state.rebalancer.get_rebalance_recommendation(current_price)


@router.post("/emergency-stop")
async def emergency_stop(
    request: EmergencyStopRequest,
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Execute emergency stop - cancel all orders and close all positions.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    try:
        result = await state.risk_manager.emergency_stop(request.reason)
        state.is_running = False
        
        await state.broadcast_update("emergency_stop", result)
        
        return result
        
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop/reset")
async def reset_emergency_stop(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Reset emergency stop to allow trading again.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    success = state.risk_manager.reset_emergency_stop()
    
    return {
        "success": success,
        "message": "Emergency stop reset" if success else "No emergency stop was active"
    }


@router.post("/price-update")
async def update_price(
    current_price: float = Query(..., gt=0, description="Current market price"),
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Update current price and check for fills (paper trading).
    
    In paper trading mode, this simulates order fills when price
    crosses order levels.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    state.position_tracker.update_prices(current_price)
    
    filled_orders = []
    if state.is_running:
        filled_orders = await state.order_manager.check_fills_at_price(current_price)
    
    rebalance_action = None
    if state.is_running:
        rebalance_action = await state.rebalancer.check_and_rebalance(current_price)
    
    risk_status = state.risk_manager.check_risk()
    
    update_data = {
        "current_price": current_price,
        "filled_orders": len(filled_orders),
        "risk_level": risk_status.level.value,
        "rebalanced": rebalance_action is not None
    }
    
    await state.broadcast_update("price_update", update_data)
    
    return {
        "current_price": current_price,
        "filled_orders": [o.to_dict() for o in filled_orders],
        "risk_status": risk_status.to_dict(),
        "rebalance_action": rebalance_action.to_dict() if rebalance_action else None
    }


@router.get("/config")
async def get_config(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get current grid configuration.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    return state.grid_calculator.config.to_dict()


@router.get("/alerts")
async def get_alerts(
    active_only: bool = Query(default=True, description="Return only active alerts"),
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Get risk alerts.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    if active_only:
        alerts = state.risk_manager.active_alerts
    else:
        alerts = state.risk_manager.alerts
    
    return {
        "alerts": [a.to_dict() for a in alerts],
        "total": len(alerts)
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Acknowledge a risk alert.
    """
    if not state.is_initialized:
        raise HTTPException(status_code=400, detail="Grid not initialized")
    
    success = state.risk_manager.acknowledge_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"success": True, "message": "Alert acknowledged"}


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    state: GridEngineState = Depends(get_engine_state)
):
    """
    WebSocket endpoint for real-time updates.
    
    Clients receive:
    - Price updates
    - Order fills
    - Position changes
    - Risk alerts
    - Rebalance events
    """
    await websocket.accept()
    state._websocket_clients.append(websocket)
    
    logger.info(f"WebSocket client connected. Total clients: {len(state._websocket_clients)}")
    
    try:
        await websocket.send_json({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected to Grid Trading WebSocket"
        })
        
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            elif data.get("type") == "subscribe":
                await websocket.send_json({
                    "type": "subscribed",
                    "channels": data.get("channels", ["all"]),
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            elif data.get("type") == "get_status":
                if state.is_initialized:
                    await websocket.send_json({
                        "type": "status",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {
                            "grid": state.grid_calculator.get_status(),
                            "orders": state.order_manager.get_status(),
                            "metrics": state.position_tracker.get_metrics(),
                            "risk": state.risk_manager.check_risk().to_dict(),
                            "is_running": state.is_running
                        }
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Grid not initialized"
                    })
                    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in state._websocket_clients:
            state._websocket_clients.remove(websocket)


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def health_check(
    state: GridEngineState = Depends(get_engine_state)
):
    """
    Health check endpoint for the grid trading engine.
    """
    return {
        "status": "healthy",
        "initialized": state.is_initialized,
        "running": state.is_running,
        "websocket_clients": len(state._websocket_clients),
        "timestamp": datetime.utcnow().isoformat()
    }
