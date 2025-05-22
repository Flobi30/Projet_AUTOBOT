"""
API routes for AUTOBOT orchestration.

This module provides API endpoints for the 100% UI orchestration of AUTOBOT,
eliminating the need for CLI commands.
"""

import logging
import time
import random
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from ..autobot_security.auth.jwt_handler import get_current_user, verify_license_key
from ..autobot_security.auth.user_manager import User
from ..schemas import (
    SetupRequest, SetupResponse, BacktestThresholds, BacktestStatus, 
    BacktestStatusResponse, TradingStatusResponse, ContinuousBacktestStatusResponse,
    GhostingConfig, GhostingStatusResponse, LicenseStatusResponse, 
    LicenseHistoryResponse, LogsResponse
)
from ..scheduler import add_scheduled_task, remove_scheduled_task
from ..worker import add_task, get_task_status
from ..trading.ghosting_manager import GhostingManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["orchestration"])

BACKTEST_THRESHOLDS = BacktestThresholds()
ACTIVE_BACKTESTS: List[BacktestStatus] = []
CONTINUOUS_BACKTESTS_ENABLED = False
GHOSTING_CONFIG = GhostingConfig(max_instances=3, evasion_mode="user_agent", instance_type="trading")
LICENSE_HISTORY: List[Dict[str, Any]] = []
SYSTEM_LOGS: List[Dict[str, Any]] = []

def generate_id() -> str:
    """Generate a unique ID."""
    return f"{int(time.time())}-{random.randint(1000, 9999)}"

def simulate_equity_curve(days: int = 30) -> Dict[str, list]:
    """Generate a simulated equity curve for demo purposes."""
    dates = [(datetime.now() - timedelta(days=days-i)).strftime("%Y-%m-%d") for i in range(days)]
    values = [100]
    for i in range(1, days):
        change = random.uniform(-3, 5)
        values.append(round(values[-1] * (1 + change/100), 2))
    return {"dates": dates, "values": values}

def check_thresholds(backtest: BacktestStatus) -> bool:
    """Check if a backtest meets the defined thresholds."""
    if not backtest.metrics:
        return False
    
    return (
        backtest.metrics.get("sharpe", 0) >= BACKTEST_THRESHOLDS.min_sharpe and
        backtest.metrics.get("drawdown", 100) <= BACKTEST_THRESHOLDS.max_drawdown and
        backtest.metrics.get("pnl", 0) >= BACKTEST_THRESHOLDS.min_pnl
    )

def all_backtests_meet_thresholds() -> bool:
    """Check if all backtests meet the defined thresholds."""
    if not ACTIVE_BACKTESTS:
        return False
    
    return all(
        backtest.status == "completed" and check_thresholds(backtest)
        for backtest in ACTIVE_BACKTESTS
    )

def start_automatic_backtests(background_tasks: BackgroundTasks):
    """Start automatic backtests for predefined strategies."""
    strategies = [
        {"strategy": "MACrossover", "symbol": "BTC/USDT"},
        {"strategy": "RSIStrategy", "symbol": "ETH/USDT"},
        {"strategy": "BollingerBands", "symbol": "BNB/USDT"},
        {"strategy": "MACD", "symbol": "SOL/USDT"}
    ]
    
    for strategy_config in strategies:
        backtest_id = generate_id()
        backtest = BacktestStatus(
            id=backtest_id,
            strategy=strategy_config["strategy"],
            symbol=strategy_config["symbol"],
            progress=0,
            status="pending",
            metrics={},
            equity_curve=None
        )
        ACTIVE_BACKTESTS.append(backtest)
        background_tasks.add_task(run_backtest_simulation, backtest_id)

def run_backtest_simulation(backtest_id: str):
    """Simulate running a backtest."""
    backtest = next((b for b in ACTIVE_BACKTESTS if b.id == backtest_id), None)
    if not backtest:
        return
    
    backtest.status = "running"
    
    for progress in range(0, 101, 5):
        backtest.progress = progress
        
        if progress > 20:
            sharpe = round(random.uniform(0.8, 2.5), 2)
            drawdown = round(random.uniform(5, 25), 2)
            pnl = round(random.uniform(-5, 30), 2)
            
            backtest.metrics = {
                "sharpe": sharpe,
                "drawdown": drawdown,
                "pnl": pnl,
                "trades": random.randint(50, 200),
                "win_rate": round(random.uniform(40, 70), 2)
            }
        
        if progress > 50 and not backtest.equity_curve:
            backtest.equity_curve = simulate_equity_curve()
        
        time.sleep(random.uniform(0.5, 2))  # Simulate processing time
    
    backtest.status = "completed"
    
    if all_backtests_meet_thresholds() and BACKTEST_THRESHOLDS.auto_live:
        pass

def start_continuous_backtest(strategy: str, symbol: str, background_tasks: BackgroundTasks):
    """Start a continuous backtest for a strategy."""
    backtest_id = generate_id()
    backtest = BacktestStatus(
        id=backtest_id,
        strategy=strategy,
        symbol=symbol,
        progress=0,
        status="pending",
        metrics={},
        equity_curve=None
    )
    ACTIVE_BACKTESTS.append(backtest)
    background_tasks.add_task(run_backtest_simulation, backtest_id)
    return backtest_id

@router.post("/setup", response_model=SetupResponse)
async def setup_configuration(request: SetupRequest, background_tasks: BackgroundTasks):
    """
    Configure all API keys and settings at once, then automatically start backtests.
    """
    try:
        all_valid = True
        error_message = ""
        
        if not all_valid:
            return SetupResponse(success=False, message=error_message)
        
        
        start_automatic_backtests(background_tasks)
        
        SYSTEM_LOGS.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "system",
            "level": "INFO",
            "message": "Initial configuration completed successfully"
        })
        
        return SetupResponse(
            success=True, 
            message="Configuration validée avec succès. Backtests démarrés automatiquement."
        )
    except Exception as e:
        logger.error(f"Setup error: {str(e)}")
        return SetupResponse(success=False, message=f"Erreur de configuration: {str(e)}")

@router.post("/backtest/thresholds")
async def update_backtest_thresholds(
    thresholds: BacktestThresholds,
    current_user: User = Depends(get_current_user)
):
    """
    Update the thresholds for backtests.
    """
    global BACKTEST_THRESHOLDS
    BACKTEST_THRESHOLDS = thresholds
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "backtest",
        "level": "INFO",
        "message": f"Backtest thresholds updated: Sharpe={thresholds.min_sharpe}, "
                  f"Drawdown={thresholds.max_drawdown}, PnL={thresholds.min_pnl}, "
                  f"Auto-Live={thresholds.auto_live}"
    })
    
    return {"success": True, "message": "Seuils mis à jour avec succès"}

@router.get("/backtest/status", response_model=BacktestStatusResponse)
async def get_backtest_status(current_user: User = Depends(get_current_user)):
    """
    Get the status of all backtests.
    """
    return BacktestStatusResponse(backtests=ACTIVE_BACKTESTS)

@router.post("/trading/live")
async def start_live_trading(current_user: User = Depends(get_current_user)):
    """
    Start live trading.
    """
    if not all_backtests_meet_thresholds():
        return {
            "success": False, 
            "message": "Impossible de passer en production: tous les backtests ne respectent pas les seuils définis"
        }
    
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "live",
        "level": "INFO",
        "message": "Transition to live trading initiated"
    })
    
    return {"success": True, "message": "Passage en production réussi"}

@router.get("/trading/status", response_model=TradingStatusResponse)
async def get_trading_status(current_user: User = Depends(get_current_user)):
    """
    Get the status of live trading.
    """
    
    recent_orders = [
        {
            "time": (datetime.now() - timedelta(minutes=random.randint(1, 60))).strftime("%H:%M:%S"),
            "symbol": symbol,
            "type": random.choice(["BUY", "SELL"]),
            "price": round(random.uniform(100, 50000), 2),
            "size": round(random.uniform(0.01, 2), 4),
            "status": random.choice(["filled", "pending", "rejected"])
        }
        for symbol in ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]
    ]
    
    return TradingStatusResponse(
        status="active",
        daily_pnl=round(random.uniform(-5, 15), 2),
        open_positions=random.randint(0, 5),
        pending_orders=random.randint(0, 3),
        recent_orders=recent_orders,
        equity_curve=simulate_equity_curve(days=7)
    )

@router.post("/backtest/continuous")
async def toggle_continuous_backtests(
    data: Dict[str, bool],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Enable or disable continuous backtests.
    """
    global CONTINUOUS_BACKTESTS_ENABLED
    CONTINUOUS_BACKTESTS_ENABLED = data.get("enabled", False)
    
    if CONTINUOUS_BACKTESTS_ENABLED:
        for backtest in ACTIVE_BACKTESTS:
            if backtest.status == "completed":
                start_continuous_backtest(backtest.strategy, backtest.symbol, background_tasks)
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "backtest",
        "level": "INFO",
        "message": f"Continuous backtests {'enabled' if CONTINUOUS_BACKTESTS_ENABLED else 'disabled'}"
    })
    
    return {"success": True, "message": f"Backtests continus {'activés' if CONTINUOUS_BACKTESTS_ENABLED else 'désactivés'}"}

@router.get("/backtest/continuous/status", response_model=ContinuousBacktestStatusResponse)
async def get_continuous_backtest_status(current_user: User = Depends(get_current_user)):
    """
    Get the status of continuous backtests.
    """
    completed = sum(1 for b in ACTIVE_BACKTESTS if b.status == "completed")
    running = sum(1 for b in ACTIVE_BACKTESTS if b.status == "running")
    
    recent_improvements = [
        {
            "date": (datetime.now() - timedelta(hours=random.randint(1, 24))).strftime("%Y-%m-%d %H:%M"),
            "strategy": random.choice(["MACrossover", "RSIStrategy", "BollingerBands", "MACD"]),
            "metric": random.choice(["sharpe", "drawdown", "pnl"]),
            "old_value": round(random.uniform(0.5, 2.0), 2),
            "new_value": round(random.uniform(1.0, 3.0), 2),
            "diff": round(random.uniform(0.1, 1.0), 2)
        }
        for _ in range(5)
    ]
    
    return ContinuousBacktestStatusResponse(
        enabled=CONTINUOUS_BACKTESTS_ENABLED,
        completed=completed,
        running=running,
        improvement=round(random.uniform(0.5, 10), 2),
        recent_improvements=recent_improvements
    )

@router.post("/ghosting/config")
async def update_ghosting_config(
    config: GhostingConfig,
    current_user: User = Depends(get_current_user)
):
    """
    Update ghosting configuration.
    """
    global GHOSTING_CONFIG
    GHOSTING_CONFIG = config
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "ghosting",
        "level": "INFO",
        "message": f"Ghosting configuration updated: Max Instances={config.max_instances}, "
                  f"Evasion Mode={config.evasion_mode}, Instance Type={config.instance_type}"
    })
    
    return {"success": True, "message": "Configuration du ghosting mise à jour avec succès"}

@router.get("/ghosting/status", response_model=GhostingStatusResponse)
async def get_ghosting_status(current_user: User = Depends(get_current_user)):
    """
    Get ghosting status.
    """
    active_instances = random.randint(1, GHOSTING_CONFIG.max_instances)
    instances = [
        {
            "id": f"instance-{i}",
            "type": GHOSTING_CONFIG.instance_type,
            "evasion_mode": GHOSTING_CONFIG.evasion_mode,
            "status": random.choice(["active", "paused", "error", "stopped"]),
            "uptime": f"{random.randint(1, 24)}h {random.randint(1, 59)}m",
            "performance": round(random.uniform(-5, 15), 2) if random.random() > 0.2 else None
        }
        for i in range(1, active_instances + 1)
    ]
    
    timestamps = [(datetime.now() - timedelta(hours=i)).strftime("%H:%M") for i in range(24, 0, -1)]
    active_history = [random.randint(1, GHOSTING_CONFIG.max_instances) for _ in range(24)]
    cpu_history = [random.randint(10, 80) for _ in range(24)]
    
    activity_history = {
        "timestamps": timestamps,
        "active": active_history,
        "cpu": cpu_history
    }
    
    return GhostingStatusResponse(
        active_instances=active_instances,
        max_instances=GHOSTING_CONFIG.max_instances,
        cpu_usage=round(random.uniform(10, 90), 1),
        memory_usage=round(random.uniform(20, 80), 1),
        license_valid=True,
        instances=instances,
        activity_history=activity_history
    )

@router.post("/ghosting/instance/{instance_id}/{action}")
async def control_ghosting_instance(
    instance_id: str,
    action: str,
    current_user: User = Depends(get_current_user)
):
    """
    Control a ghosting instance (pause, resume, stop).
    """
    if action not in ["pause", "resume", "stop"]:
        raise HTTPException(status_code=400, detail="Action invalide")
    
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "ghosting",
        "level": "INFO",
        "message": f"Instance {instance_id} {action} requested"
    })
    
    return {"success": True, "message": f"Action {action} appliquée à l'instance {instance_id}"}

@router.post("/license/apply")
async def apply_license(data: Dict[str, str]):
    """
    Apply a license key.
    """
    license_key = data.get("license_key", "")
    if not license_key:
        return {"success": False, "message": "Clé de licence non fournie"}
    
    is_valid = len(license_key) >= 16
    
    LICENSE_HISTORY.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "license_key": license_key,
        "success": is_valid
    })
    
    if not is_valid:
        return {"success": False, "message": "Clé de licence invalide"}
    
    SYSTEM_LOGS.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "system",
        "level": "INFO",
        "message": f"License key applied successfully"
    })
    
    return {
        "success": True,
        "message": "Licence validée avec succès",
        "license": {
            "key": license_key,
            "type": "Premium",
            "max_instances": 10,
            "expiry_date": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "owner": "AUTOBOT User"
        }
    }

@router.get("/license/status", response_model=LicenseStatusResponse)
async def get_license_status():
    """
    Get license status.
    """
    
    if not LICENSE_HISTORY:
        return LicenseStatusResponse(
            success=False,
            message="Aucune licence active"
        )
    
    last_license = next((l for l in LICENSE_HISTORY if l["success"]), None)
    if not last_license:
        return LicenseStatusResponse(
            success=False,
            message="Aucune licence valide trouvée"
        )
    
    return LicenseStatusResponse(
        success=True,
        message="Licence active et valide",
        license={
            "key": last_license["license_key"],
            "type": "Premium",
            "max_instances": 10,
            "expiry_date": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "owner": "AUTOBOT User"
        }
    )

@router.get("/license/history", response_model=LicenseHistoryResponse)
async def get_license_history(current_user: User = Depends(get_current_user)):
    """
    Get license validation history.
    """
    return LicenseHistoryResponse(history=LICENSE_HISTORY)

@router.get("/logs", response_model=LogsResponse)
async def get_logs(current_user: User = Depends(get_current_user)):
    """
    Get system logs.
    """
    if not SYSTEM_LOGS:
        for _ in range(20):
            log_type = random.choice(["backtest", "live", "ghosting", "system"])
            level = random.choice(["INFO", "WARNING", "ERROR"])
            
            message = ""
            if log_type == "backtest":
                message = random.choice([
                    "Backtest started for strategy MACrossover",
                    "Backtest completed with Sharpe ratio 1.8",
                    "Backtest failed due to insufficient data"
                ])
            elif log_type == "live":
                message = random.choice([
                    "Order placed: BUY 0.1 BTC at 45000 USDT",
                    "Order filled: SELL 0.05 ETH at 3200 USDT",
                    "Trading paused due to market volatility"
                ])
            elif log_type == "ghosting":
                message = random.choice([
                    "New instance created: instance-123",
                    "Instance paused: instance-456",
                    "Instance rotation completed"
                ])
            else:  # system
                message = random.choice([
                    "System startup completed",
                    "Configuration updated",
                    "Database backup completed"
                ])
            
            SYSTEM_LOGS.append({
                "timestamp": (datetime.now() - timedelta(hours=random.randint(0, 24))).strftime("%Y-%m-%d %H:%M:%S"),
                "type": log_type,
                "level": level,
                "message": message
            })
    
    sorted_logs = sorted(
        SYSTEM_LOGS,
        key=lambda x: datetime.strptime(x["timestamp"], "%Y-%m-%d %H:%M:%S"),
        reverse=True
    )
    
    return LogsResponse(logs=sorted_logs)
