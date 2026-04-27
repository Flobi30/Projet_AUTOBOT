"""
FastAPI Dashboard Server - Expose les données du bot en temps réel
CORRECTIONS: Auth, thread-safety, graceful shutdown, error handling
"""

import logging
import os
import hmac
import time
import threading
import inspect
import heapq
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# CORRECTION: Sécurité - Token Bearer pour auth
security = HTTPBearer(auto_error=False)



def _compute_global_totals(orchestrator: Any, status: Dict[str, Any]) -> tuple[float, float]:
    """Derive total capital/profit with safe, non-fake fallbacks."""
    instances = status.get('instances', [])
    total_capital = sum(float(inst.get('capital', 0.0)) for inst in instances)

    total_profit = None
    if instances and all(isinstance(inst, dict) and ('profit' in inst) for inst in instances):
        total_profit = sum(float(inst.get('profit', 0.0)) for inst in instances)
    elif hasattr(orchestrator, 'get_instances_snapshot'):
        snapshot = orchestrator.get_instances_snapshot()
        if isinstance(snapshot, list):
            total_profit = sum(float(inst.get('profit', 0.0)) for inst in snapshot if isinstance(inst, dict))

    if total_profit is None:
        total_profit = 0.0

    return total_capital, total_profit


async def _stop_orchestrator_safely(orchestrator: Any) -> None:
    """Execute stop path and confirm stop state before returning success."""
    stop_result = orchestrator.stop()
    if inspect.isawaitable(stop_result):
        await stop_result

    try:
        post_status = orchestrator.get_status()
        if post_status.get("running", True):
            raise HTTPException(status_code=503, detail="Arrêt d'urgence non confirmé")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Arrêt d'urgence non confirmé")

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Vérifie le token API.

    - En mode development (APP_ENV=development) : token facultatif.
    - En tout autre environnement : token obligatoire.
    """
    app_env = os.getenv('APP_ENV', 'production').lower()
    expected_token = os.getenv('DASHBOARD_API_TOKEN')

    # Mode development uniquement si explicitement autorisé
    allow_insecure_dev = os.getenv('ALLOW_INSECURE_DEV_AUTH', 'false').lower() == 'true'
    if app_env == 'development' and not expected_token and allow_insecure_dev:
        return True

    # Hors development OU token configuré : authentification obligatoire
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="DASHBOARD_API_TOKEN non configuré — accès refusé en production"
        )

    received_token = credentials.credentials.strip()
    configured_token = expected_token.strip()

    if not hmac.compare_digest(received_token, configured_token):
        logger.warning("Token mismatch from client")
        raise HTTPException(status_code=403, detail="Token invalide")

    return True

# Modèles Pydantic pour les réponses
class InstanceStatus(BaseModel):
    id: str
    name: str
    capital: float
    profit: float
    status: str
    strategy: str
    open_positions: int
    warmup: Optional[Dict[str, Any]] = None
    blocked_reasons: List[str] = []

class GlobalStatus(BaseModel):
    running: bool
    instance_count: int
    total_capital: float
    total_profit: float
    websocket_connected: bool
    uptime_seconds: Optional[float]

class PositionInfo(BaseModel):
    pair: str
    side: str
    size: str
    entry_price: float
    current_price: float
    pnl: float
    pnl_percent: float

class EmergencyStopRequest(BaseModel):
    confirmation: str  # Doit être "CONFIRM_STOP"

# Application FastAPI
app = FastAPI(
    title="AUTOBOT V2 Dashboard API",
    description="API pour le dashboard de monitoring du bot de trading",
    version="2.0.0"
)

# SEC-06: CORS origins configurable via env var for production restriction
_cors_env = os.getenv('DASHBOARD_CORS_ORIGINS', 'http://localhost:5173,http://localhost:3000')
_cors_origins = [o.strip() for o in _cors_env.split(',') if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # CORRECTION: Pas "*"
    allow_headers=["Content-Type", "Authorization"],  # CORRECTION: Pas "*"
)
@app.get("/health")
async def health_check(request: Request):
    """
    Health check pour Docker et monitoring.
    Vérifie l'état de tous les composants.
    """
    # SEC-13: simple rate limiter — max 10 req/s per IP
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    _health_calls = getattr(app.state, '_health_calls', {})
    calls = [t for t in _health_calls.get(client_ip, []) if now - t < 1.0]
    if len(calls) >= 10:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    calls.append(now)
    _health_calls[client_ip] = calls
    app.state._health_calls = _health_calls

    orchestrator = getattr(request.app.state, 'orchestrator', None)

    if not orchestrator:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orchestrator": "not_initialized",
            "websocket": "unknown"
        }

    try:
        status = orchestrator.get_status()

        is_healthy = (
            status.get('running', False) and
            status.get('websocket_connected', False)
        )

        return {
            "status": "healthy" if is_healthy else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "2.0.0",
            "components": {
                "orchestrator": "running" if status.get('running') else "stopped",
                "websocket": "connected" if status.get('websocket_connected') else "disconnected",
                "instances": status.get('instance_count', 0),
                "uptime_seconds": status.get('uptime_seconds')
            }
        }
    except Exception as e:
        logger.exception("Erreur health check")
        return {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@app.get("/api/status", response_model=GlobalStatus)
async def get_global_status(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Retourne le statut global du bot"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        # CORRECTION: Utilise méthode thread-safe
        status = orchestrator.get_status()
        instances = status.get('instances', [])
        capital_snapshot = status.get('capital') or {}
        if capital_snapshot.get("source_status") == "ok":
            total_capital = float(capital_snapshot.get("total_capital", 0.0))
            total_profit = float(capital_snapshot.get("total_profit", 0.0))
        else:
            total_capital = sum(float(inst.get('capital', 0.0)) for inst in instances)

            total_profit = None
            if instances and all(isinstance(inst, dict) and ('profit' in inst) for inst in instances):
                total_profit = sum(float(inst.get('profit', 0.0)) for inst in instances)
            elif hasattr(orchestrator, 'get_instances_snapshot'):
                snapshot = orchestrator.get_instances_snapshot()
                if isinstance(snapshot, list):
                    total_profit = sum(float(inst.get('profit', 0.0)) for inst in snapshot if isinstance(inst, dict))

            if total_profit is None:
                raise HTTPException(status_code=500, detail="Erreur interne")

        return GlobalStatus(
            running=status['running'],
            instance_count=status['instance_count'],
            total_capital=total_capital,
            total_profit=total_profit,
            websocket_connected=status['websocket_connected'],
            uptime_seconds=(datetime.now(timezone.utc) - status['start_time']).total_seconds() if status['start_time'] else None
        )
    except Exception:
        logger.exception("Erreur récupération statut global")
        # CORRECTION: Ne pas exposer détails de l'erreur
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/scaling/status")
async def get_scaling_status(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Scaling status (scalability guard + activation manager)."""
    from ..config import ENABLE_SCALABILITY_GUARD, ENABLE_INSTANCE_ACTIVATION_MANAGER

    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        status = orchestrator.get_status()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": bool(ENABLE_SCALABILITY_GUARD or ENABLE_INSTANCE_ACTIVATION_MANAGER),
            "guard_enabled": bool(ENABLE_SCALABILITY_GUARD),
            "activation_enabled": bool(ENABLE_INSTANCE_ACTIVATION_MANAGER),
            "guard": status.get("scalability_guard") or {
                "state": "DISABLED",
                "reasons": ["Feature disabled by configuration"],
                "signals": {},
            },
            "activation": status.get("activation") or {
                "action": "hold",
                "target_instances": status.get("instance_count", 0),
                "target_tier": 1,
                "selected_symbols": [],
                "reason": "Feature disabled by configuration",
            },
            "explanation": {
                "decision": (status.get("activation") or {}).get("action", "hold"),
                "reason": (status.get("activation") or {}).get("reason", "Feature disabled by configuration"),
                "guard_state": (status.get("scalability_guard") or {}).get("state", "DISABLED"),
                "guard_reasons": (status.get("scalability_guard") or {}).get("reasons", ["Feature disabled by configuration"]),
            },
            "message": None if (ENABLE_SCALABILITY_GUARD or ENABLE_INSTANCE_ACTIVATION_MANAGER) else "Feature disabled by configuration",
        }
    except Exception:
        logger.exception("Erreur récupération scaling status")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/universe/status")
async def get_universe_status(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Universe/ranking runtime status."""
    from ..config import ENABLE_UNIVERSE_MANAGER, ENABLE_PAIR_RANKING_ENGINE

    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        manager = getattr(orchestrator, "universe_manager", None)
        if not ENABLE_UNIVERSE_MANAGER or manager is None:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "enabled": False,
                "message": "Feature disabled by configuration",
                "counts": {
                    "supported": 0,
                    "eligible": 0,
                    "ranked": 0,
                    "websocket_active": 0,
                    "actively_traded": 0,
                },
                "ranking_enabled": bool(ENABLE_PAIR_RANKING_ENGINE),
            }

        snap = manager.snapshot()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "ranking_enabled": bool(ENABLE_PAIR_RANKING_ENGINE),
            "counts": {
                "supported": len(snap.supported),
                "eligible": len(snap.eligible),
                "ranked": len(snap.ranked),
                "websocket_active": len(snap.websocket_active),
                "actively_traded": len(snap.actively_traded),
            },
            "top_ranked": list(snap.ranked[:10]),
        }
    except Exception:
        logger.exception("Erreur récupération universe status")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/opportunities/top")
async def get_top_opportunities(
    request: Request,
    limit: int = 10,
    authorized: bool = Depends(verify_token)
):
    """Top ranked opportunities with score/explain payload."""
    from ..config import ENABLE_PAIR_RANKING_ENGINE

    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        if not ENABLE_PAIR_RANKING_ENGINE:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "enabled": False,
                "message": "Feature disabled by configuration",
                "opportunities": [],
            }

        ranking_engine = getattr(orchestrator, "pair_ranking_engine", None)
        universe_manager = getattr(orchestrator, "universe_manager", None)

        opportunities = []
        if ranking_engine is not None:
            ranked = ranking_engine.get_ranked_pairs()
            opportunities = [
                {
                    "symbol": p.symbol,
                    "score": p.score,
                    "explain": p.explain,
                }
                for p in ranked[: max(1, min(limit, 50))]
            ]
        elif universe_manager is not None:
            scored = universe_manager.get_scored_universe()
            ranked = universe_manager.get_ranked_universe()
            for sym in ranked[: max(1, min(limit, 50))]:
                opportunities.append({
                    "symbol": sym,
                    "score": float(scored.get(sym, {}).get("score", 0.0)),
                    "explain": dict(scored.get(sym, {})),
                })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "opportunities": opportunities,
        }
    except Exception:
        logger.exception("Erreur récupération opportunities")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/portfolio/allocation")
async def get_portfolio_allocation(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Current portfolio allocation plan/caps."""
    from ..config import ENABLE_PORTFOLIO_ALLOCATOR

    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        status = orchestrator.get_status()
        alloc = status.get("portfolio_allocator") or {"enabled": False, "plan": None}
        if not ENABLE_PORTFOLIO_ALLOCATOR:
            alloc = {"enabled": False, "plan": None}

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": bool(alloc.get("enabled", False)),
            "message": None if bool(alloc.get("enabled", False)) else "Feature disabled by configuration",
            "allocation": alloc.get("plan"),
            "constraints": ((alloc.get("plan") or {}).get("explain") if alloc.get("plan") else None),
        }
    except Exception:
        logger.exception("Erreur récupération portfolio allocation")
        raise HTTPException(status_code=500, detail="Erreur interne")

@app.get("/api/instances", response_model=List[InstanceStatus])
async def get_instances(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Liste toutes les instances actives"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        # CORRECTION: Utilise méthode thread-safe
        instances_data = orchestrator.get_instances_snapshot()
        return [
            InstanceStatus(
                id=inst['id'],
                name=inst['name'],
                capital=inst['capital'],
                profit=inst['profit'],
                status=inst['status'],
                strategy=inst['strategy'],
                open_positions=inst['open_positions'],
                warmup=inst.get('warmup'),
                blocked_reasons=inst.get('blocked_reasons', []),
            )
            for inst in instances_data
        ]
    except Exception:
        logger.exception("Erreur récupération instances")
        raise HTTPException(status_code=500, detail="Erreur interne")

@app.get("/api/instances/{instance_id}/positions", response_model=List[PositionInfo])
async def get_instance_positions(
    instance_id: str,
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Retourne les positions ouvertes d'une instance"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        # CORRECTION: Utilise méthode thread-safe
        positions = orchestrator.get_instance_positions_snapshot(instance_id)
        if positions is None:
            raise HTTPException(status_code=404, detail="Instance non trouvée")
        
        return [
            PositionInfo(
                pair=pos['pair'],
                side=pos['side'],
                size=pos['size'],
                entry_price=pos['entry_price'],
                current_price=pos['current_price'],
                pnl=pos['pnl'],
                pnl_percent=pos['pnl_percent']
            )
            for pos in positions
        ]
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Erreur récupération positions instance {instance_id}")
        raise HTTPException(status_code=500, detail="Erreur interne")

@app.post("/api/emergency-stop")
async def emergency_stop(
    request: Request,
    stop_req: EmergencyStopRequest,
    authorized: bool = Depends(verify_token)
):
    """
    Arrêt d'urgence - ferme toutes les instances
    CORRECTION: Nécessite confirmation explicite
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    # CORRECTION: Vérification confirmation
    if stop_req.confirmation != "CONFIRM_STOP":
        raise HTTPException(
            status_code=400, 
            detail="Confirmation requise: confirmation='CONFIRM_STOP'"
        )
    
    try:
        logger.warning("🚨 ARRÊT D'URGENCE demandé via Dashboard!")
        stop_result = orchestrator.stop()
        if inspect.isawaitable(stop_result):
            await stop_result

        try:
            post_status = orchestrator.get_status()
            if post_status.get("running", True):
                raise HTTPException(status_code=503, detail="Arrêt d'urgence non confirmé")
        except HTTPException:
            raise
        except Exception:
            # If status is unavailable after stop handling, preserve safety-first semantics.
            raise HTTPException(status_code=503, detail="Arrêt d'urgence non confirmé")

        return {
            "message": "Arrêt d'urgence exécuté",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "stopped"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erreur arrêt d'urgence")
        raise HTTPException(status_code=500, detail="Erreur interne")


# === NOUVEAUX ENDPOINTS PHASE 9 ===

@app.get("/api/performance")
async def get_performance(request: Request, authorized: bool = Depends(verify_token)):
    """PF global et par instance - rendement, Sharpe, win rate"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        instances_data = orchestrator.get_instances_snapshot()
        total_capital = sum(inst.get('capital', 0) for inst in instances_data)
        total_profit = sum(inst.get('profit', 0) for inst in instances_data)
        total_initial = sum(inst.get('initial_capital', inst.get('capital', 0)) for inst in instances_data)

        # Performance globale
        global_pnl_pct = (total_profit / total_initial * 100) if total_initial > 0 else 0.0

        # Performance par instance
        per_instance = []
        for inst in instances_data:
            initial = inst.get('initial_capital', inst.get('capital', 0))
            profit = inst.get('profit', 0)
            pnl_pct = (profit / initial * 100) if initial > 0 else 0.0

            trades = inst.get('trades_history', [])
            total_trades = len(trades)
            winning = sum(1 for t in trades if t.get('pnl', 0) > 0)
            win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0

            # Sharpe simplifié (si données disponibles)
            sharpe = inst.get('sharpe_ratio', None)

            per_instance.append({
                "id": inst['id'],
                "name": inst.get('name', inst['id']),
                "capital": inst.get('capital', 0),
                "profit": profit,
                "pnl_percent": round(pnl_pct, 2),
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
                "strategy": inst.get('strategy', 'unknown'),
                "status": inst.get('status', 'unknown')
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "global": {
                "total_capital": round(total_capital, 2),
                "total_profit": round(total_profit, 2),
                "pnl_percent": round(global_pnl_pct, 2),
                "instance_count": len(instances_data)
            },
            "instances": per_instance
        }
    except Exception:
        logger.exception("Erreur récupération performance")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/performance/persisted")
async def get_performance_persisted(authorized: bool = Depends(verify_token)):
    """Persisted PF/expectancy based on immutable trade ledger."""
    try:
        from ..persistence import get_persistence

        metrics = get_persistence().get_trade_ledger_metrics()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "trade_ledger",
            "metrics": metrics,
        }
    except Exception:
        logger.exception("Erreur récupération performance persistée")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/drawdown")
async def get_drawdown(request: Request, authorized: bool = Depends(verify_token)):
    """Max drawdown et current drawdown par instance et global"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        instances_data = orchestrator.get_instances_snapshot()

        per_instance = []
        global_peak = 0.0
        global_current = 0.0

        for inst in instances_data:
            capital = inst.get('capital', 0)
            peak_capital = inst.get('peak_capital', capital)
            initial_capital = inst.get('initial_capital', capital)
            max_drawdown = inst.get('max_drawdown', 0.0)

            # Current drawdown depuis le pic
            current_dd = 0.0
            if peak_capital > 0:
                current_dd = (peak_capital - capital) / peak_capital * 100

            # Max drawdown (historique ou calculé)
            max_dd = max(max_drawdown, current_dd)

            global_peak += peak_capital
            global_current += capital

            per_instance.append({
                "id": inst['id'],
                "name": inst.get('name', inst['id']),
                "capital": round(capital, 2),
                "peak_capital": round(peak_capital, 2),
                "current_drawdown_pct": round(current_dd, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "strategy": inst.get('strategy', 'unknown')
            })

        # Drawdown global
        global_current_dd = 0.0
        if global_peak > 0:
            global_current_dd = (global_peak - global_current) / global_peak * 100

        global_max_dd = max(
            (inst.get('max_drawdown', 0.0) for inst in instances_data),
            default=0.0
        )
        global_max_dd = max(global_max_dd, global_current_dd)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "global": {
                "total_peak_capital": round(global_peak, 2),
                "total_current_capital": round(global_current, 2),
                "current_drawdown_pct": round(global_current_dd, 2),
                "max_drawdown_pct": round(global_max_dd, 2)
            },
            "instances": per_instance
        }
    except Exception:
        logger.exception("Erreur récupération drawdown")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/shadow-status")
async def get_shadow_status(request: Request, authorized: bool = Depends(verify_token)):
    """État du shadow trading - mode paper vs live, comparaison"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        instances_data = orchestrator.get_instances_snapshot()

        shadow_instances = []
        live_instances = []

        for inst in instances_data:
            mode = inst.get('trading_mode', 'unknown')
            entry = {
                "id": inst['id'],
                "name": inst.get('name', inst['id']),
                "strategy": inst.get('strategy', 'unknown'),
                "capital": inst.get('capital', 0),
                "profit": inst.get('profit', 0),
                "status": inst.get('status', 'unknown'),
                "open_positions": inst.get('open_positions', 0),
                "total_trades": len(inst.get('trades_history', [])),
                "started_at": inst.get('started_at', None)
            }

            if mode in ('shadow', 'paper', 'dry_run'):
                shadow_instances.append(entry)
            else:
                live_instances.append(entry)

        # Comparaison shadow vs live si les deux existent
        shadow_profit = sum(i.get('profit', 0) for i in shadow_instances)
        live_profit = sum(i.get('profit', 0) for i in live_instances)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "shadow_mode_active": len(shadow_instances) > 0,
            "summary": {
                "shadow_count": len(shadow_instances),
                "live_count": len(live_instances),
                "shadow_total_profit": round(shadow_profit, 2),
                "live_total_profit": round(live_profit, 2),
                "divergence": round(shadow_profit - live_profit, 2)
            },
            "shadow_instances": shadow_instances,
            "live_instances": live_instances
        }
    except Exception:
        logger.exception("Erreur récupération shadow status")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/phase1-modules")
async def get_phase1_modules(request: Request, authorized: bool = Depends(verify_token)):
    """Statut des modules performance Phase 1"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        # Récupère l'état des modules depuis l'orchestrateur
        modules_status = {}

        # Module Risk Manager
        risk_mgr = getattr(orchestrator, 'risk_manager', None)
        modules_status['risk_manager'] = {
            "active": risk_mgr is not None,
            "status": "running" if risk_mgr else "not_loaded",
            "max_position_size": getattr(risk_mgr, 'max_position_size', None),
            "max_daily_loss": getattr(risk_mgr, 'max_daily_loss', None),
            "daily_loss_current": getattr(risk_mgr, 'daily_loss_current', None),
            "circuit_breaker_triggered": getattr(risk_mgr, 'circuit_breaker_triggered', False)
        }

        # Module Order Manager
        order_mgr = getattr(orchestrator, 'order_manager', None)
        modules_status['order_manager'] = {
            "active": order_mgr is not None,
            "status": "running" if order_mgr else "not_loaded",
            "pending_orders": getattr(order_mgr, 'pending_count', 0),
            "filled_today": getattr(order_mgr, 'filled_today', 0),
            "rejected_today": getattr(order_mgr, 'rejected_today', 0)
        }

        # Module Data Collector
        data_collector = getattr(orchestrator, 'data_collector', None)
        modules_status['data_collector'] = {
            "active": data_collector is not None,
            "status": "running" if data_collector else "not_loaded",
            "pairs_tracked": getattr(data_collector, 'pairs_count', 0),
            "last_update": getattr(data_collector, 'last_update', None),
            "buffer_size": getattr(data_collector, 'buffer_size', 0)
        }

        # Module Signal Generator
        signal_gen = getattr(orchestrator, 'signal_generator', None)
        modules_status['signal_generator'] = {
            "active": signal_gen is not None,
            "status": "running" if signal_gen else "not_loaded",
            "signals_today": getattr(signal_gen, 'signals_today', 0),
            "last_signal_time": getattr(signal_gen, 'last_signal_time', None),
            "active_signals": getattr(signal_gen, 'active_count', 0)
        }

        # Module Portfolio Manager
        portfolio_mgr = getattr(orchestrator, 'portfolio_manager', None)
        modules_status['portfolio_manager'] = {
            "active": portfolio_mgr is not None,
            "status": "running" if portfolio_mgr else "not_loaded",
            "allocation_mode": getattr(portfolio_mgr, 'allocation_mode', None),
            "rebalance_interval": getattr(portfolio_mgr, 'rebalance_interval', None),
            "last_rebalance": getattr(portfolio_mgr, 'last_rebalance', None)
        }

        # Compte global
        total = len(modules_status)
        active = sum(1 for m in modules_status.values() if m['active'])

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_modules": total,
                "active_modules": active,
                "inactive_modules": total - active,
                "health": "healthy" if active == total else ("degraded" if active > 0 else "offline")
            },
            "modules": modules_status
        }
    except Exception:
        logger.exception("Erreur récupération modules phase 1")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/strategies-dormantes")
async def get_dormant_strategies(request: Request, authorized: bool = Depends(verify_token)):
    """Stratégies dormantes - Mean Reversion, Arbitrage, etc."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        # Récupère le registre de stratégies
        strategy_registry = getattr(orchestrator, 'strategy_registry', {})
        instances_data = orchestrator.get_instances_snapshot()

        # Stratégies actives (utilisées par des instances)
        active_strategies = set(inst.get('strategy', '') for inst in instances_data)

        # Stratégies dormantes connues
        dormant_strategies = []

        # Liste de stratégies prévues (peut être étendue)
        known_strategies = {
            'mean_reversion': {
                'name': 'Mean Reversion',
                'description': 'Retour à la moyenne - exploite les déviations statistiques',
                'category': 'statistical',
                'min_capital': 500,
                'pairs_recommended': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
            },
            'arbitrage': {
                'name': 'Arbitrage',
                'description': 'Arbitrage cross-exchange et triangulaire',
                'category': 'arbitrage',
                'min_capital': 1000,
                'pairs_recommended': ['BTC/USDT', 'ETH/USDT', 'ETH/BTC']
            },
            'breakout': {
                'name': 'Breakout',
                'description': 'Détection de cassures de range et momentum',
                'category': 'momentum',
                'min_capital': 300,
                'pairs_recommended': ['BTC/USDT', 'ETH/USDT']
            },
            'grid_trading': {
                'name': 'Grid Trading',
                'description': 'Grille d\'ordres dans un range défini',
                'category': 'range',
                'min_capital': 500,
                'pairs_recommended': ['BTC/USDT', 'ETH/USDT']
            },
            'dca': {
                'name': 'DCA (Dollar Cost Averaging)',
                'description': 'Accumulation progressive avec timing optimisé',
                'category': 'accumulation',
                'min_capital': 100,
                'pairs_recommended': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
            }
        }

        # Ajoute aussi les stratégies du registre dynamique
        for key, info in strategy_registry.items():
            if key not in known_strategies:
                known_strategies[key] = {
                    'name': info.get('name', key),
                    'description': info.get('description', ''),
                    'category': info.get('category', 'custom'),
                    'min_capital': info.get('min_capital', 0),
                    'pairs_recommended': info.get('pairs', [])
                }

        for strategy_key, strategy_info in known_strategies.items():
            is_active = strategy_key in active_strategies
            # Cherche dans le registre si implémentée
            is_implemented = strategy_key in strategy_registry

            if not is_active:
                dormant_strategies.append({
                    "key": strategy_key,
                    "name": strategy_info['name'],
                    "description": strategy_info['description'],
                    "category": strategy_info['category'],
                    "status": "implemented" if is_implemented else "planned",
                    "min_capital_required": strategy_info['min_capital'],
                    "pairs_recommended": strategy_info['pairs_recommended'],
                    "ready_to_activate": is_implemented
                })

        # Stratégies actives pour référence
        active_list = [
            {
                "key": s,
                "instance_count": sum(1 for i in instances_data if i.get('strategy') == s)
            }
            for s in active_strategies if s
        ]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_known": len(known_strategies),
                "active_count": len(active_strategies - {''}),
                "dormant_count": len(dormant_strategies),
                "ready_to_activate": sum(1 for s in dormant_strategies if s['ready_to_activate'])
            },
            "dormant": dormant_strategies,
            "active": active_list
        }
    except Exception:
        logger.exception("Erreur récupération stratégies dormantes")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/capital")
async def get_capital_detail(request: Request, authorized: bool = Depends(verify_token)):
    """Détails du capital (investi, disponible, profit)"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        get_snapshot = getattr(orchestrator, 'get_capital_snapshot', None)
        if not get_snapshot:
            raise HTTPException(status_code=503, detail="Source capital indisponible")
        snapshot = await get_snapshot()
        if snapshot.get("source_status") != "ok":
            raise HTTPException(status_code=503, detail="Source capital indisponible")

        return {
            "timestamp": snapshot.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "total_capital": round(float(snapshot.get("total_capital", 0.0)), 2),
            "total_balance": round(float(snapshot.get("total_balance", 0.0)), 2),
            "allocated_capital": round(float(snapshot.get("allocated_capital", 0.0)), 2),
            "reserve_cash": round(float(snapshot.get("reserve_cash", 0.0)), 2),
            "total_profit": round(float(snapshot.get("total_profit", 0.0)), 2),
            "total_invested": round(float(snapshot.get("total_invested", 0.0)), 2),
            "available_cash": round(float(snapshot.get("available_cash", 0.0)), 2),
            "cash_balance": round(float(snapshot.get("cash_balance", 0.0)), 2),
            "open_position_notional": round(float(snapshot.get("open_position_notional", 0.0)), 2),
            "currency": snapshot.get("currency", "EUR"),
            "paper_mode": bool(snapshot.get("paper_mode", False)),
            "source": snapshot.get("source", "unknown"),
            "source_status": snapshot.get("source_status", "unknown"),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erreur récupération capital")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/trades")
async def get_trades(
    request: Request,
    authorized: bool = Depends(verify_token),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Liste des trades exécutés"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        target_window = max(offset + limit, limit)

        total_count = 0
        paginated_trades: List[Dict[str, Any]] = []

        # Preferred strategy when available: persistence-side paginated access.
        persistence = getattr(orchestrator, "persistence", None)
        if persistence is None:
            try:
                from ..persistence import get_persistence
                persistence = get_persistence()
            except Exception:
                persistence = None

        if persistence and hasattr(persistence, "get_trades_paginated"):
            persisted = persistence.get_trades_paginated(limit=limit, offset=offset)
            total_count = int(persisted.get("total", 0))
            paginated_trades = list(persisted.get("items", []))
        else:
            instances_data = orchestrator.get_instances_snapshot()
            default_ts = datetime.now(timezone.utc).isoformat()

            def _to_epoch(ts: Any) -> float:
                if not ts:
                    return 0.0
                if isinstance(ts, datetime):
                    dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                else:
                    ts_str = str(ts)
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    try:
                        dt = datetime.fromisoformat(ts_str)
                    except ValueError:
                        return 0.0
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()

            # Fallback strategy: bounded in-memory top-N to avoid full aggregation/sort.
            # We only retain the `offset + limit` newest trades globally.
            bounded_heap: List[tuple[float, int, Dict[str, Any]]] = []
            seq = 0

            for inst in instances_data:
                inst_trades = inst.get("trades_history", [])
                total_count += len(inst_trades)
                for trade in inst_trades:
                    ts_value = trade.get("timestamp", default_ts)
                    ts_epoch = _to_epoch(ts_value)
                    candidate = {
                        "id": trade.get("id", "unknown"),
                        "instance_id": inst["id"],
                        "instance_name": inst.get("name", "Unknown"),
                        "pair": trade.get("pair", "XBT/EUR"),
                        "side": trade.get("side", "BUY"),
                        "amount": trade.get("amount", 0),
                        "price": trade.get("price", 0),
                        "pnl": trade.get("pnl", 0),
                        "timestamp": ts_value,
                        "strategy": inst.get("strategy", "unknown"),
                        "_ts_epoch": ts_epoch,
                    }
                    entry = (ts_epoch, seq, candidate)
                    if len(bounded_heap) < target_window:
                        heapq.heappush(bounded_heap, entry)
                    elif entry > bounded_heap[0]:
                        heapq.heapreplace(bounded_heap, entry)
                    seq += 1

            top_window = [
                item[2] for item in sorted(
                    bounded_heap,
                    key=lambda x: (x[0], x[1]),
                    reverse=True,
                )
            ]
            paginated_trades = top_window[offset:offset + limit]
            for trade in paginated_trades:
                trade.pop("_ts_epoch", None)

        has_more = (offset + len(paginated_trades)) < total_count
        next_offset = offset + len(paginated_trades) if has_more else None

        return {
            "count": total_count,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": len(paginated_trades),
                "total": total_count,
                "has_more": has_more,
                "next_offset": next_offset,
            },
            "trades": paginated_trades
        }
    except Exception:
        logger.exception("Erreur récupération trades")
        raise HTTPException(status_code=500, detail="Erreur interne")




# =====================================================================
# PERFORMANCE ENDPOINTS — Real calculations, no mock data
# =====================================================================

@app.get("/api/performance/global")
async def get_global_performance(request: Request, authorized: bool = Depends(verify_token)):
    """
    Aggregated performance across ALL instances.
    All calculations use real data from the orchestrator.

    Returns:
        - capital_total: Sum of all current capitals
        - capital_initial: Sum of all initial capitals
        - profit_total: Computed from real instance profits
        - profit_percent: (profit / initial) * 100
        - profit_factor: gross_profit / gross_loss (real)
        - win_rate: % of winning trades (real)
        - total_trades: Count of executed trades
        - instances_count: Number of live instances
        - by_strategy: Breakdown by strategy type
        - history: Capital history points (from real data)
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        # Use extended snapshot for full data access
        get_extended = getattr(orchestrator, 'get_instances_snapshot_extended', None)
        if get_extended:
            instances_data = get_extended()
        else:
            instances_data = orchestrator.get_instances_snapshot()

        if not instances_data:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "capital_total": 0.0,
                "capital_initial": 0.0,
                "profit_total": 0.0,
                "profit_percent": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "instances_count": 0,
                "by_strategy": [],
                "history": [],
            }

        # 1. Capital calculations (REAL)
        capital_total = sum(inst.get("capital", 0) for inst in instances_data)
        capital_initial = sum(
            inst.get("initial_capital", inst.get("capital", 0))
            for inst in instances_data
        )
        profit_total = sum(inst.get("profit", 0) for inst in instances_data)
        profit_percent = (profit_total / capital_initial * 100) if capital_initial > 0 else 0.0

        # 2. Profit Factor & Win Rate (REAL — computed from actual trades)
        gross_profit = 0.0
        gross_loss = 0.0
        total_trades = 0
        winning_trades = 0

        for inst in instances_data:
            trades = inst.get("trades_history", [])
            for trade in trades:
                pnl = trade.get("profit", 0) or 0
                total_trades += 1
                if pnl > 0:
                    gross_profit += pnl
                    winning_trades += 1
                elif pnl < 0:
                    gross_loss += abs(pnl)

        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )
        # Clamp infinite PF for JSON serialization
        if profit_factor == float("inf"):
            profit_factor = 999.99
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # 3. If no trades from extended snapshot, fallback to win/loss counts
        if total_trades == 0:
            for inst in instances_data:
                wc = inst.get("win_count", 0)
                lc = inst.get("loss_count", 0)
                total_trades += wc + lc
                winning_trades += wc
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # 4. By strategy breakdown (REAL)
        strategy_map: Dict[str, Dict] = {}
        for inst in instances_data:
            strat = inst.get("strategy", "unknown")
            if strat not in strategy_map:
                strategy_map[strat] = {
                    "strategy": strat,
                    "instances_count": 0,
                    "capital_total": 0.0,
                    "profit_total": 0.0,
                }
            strategy_map[strat]["instances_count"] += 1
            strategy_map[strat]["capital_total"] += inst.get("capital", 0)
            strategy_map[strat]["profit_total"] += inst.get("profit", 0)

        by_strategy = []
        for strat_data in strategy_map.values():
            by_strategy.append({
                "strategy": strat_data["strategy"],
                "instances_count": strat_data["instances_count"],
                "capital_total": round(strat_data["capital_total"], 2),
                "profit_total": round(strat_data["profit_total"], 2),
            })

        # 5. History — aggregate capital snapshots from instance data
        # (Uses real profit from each instance to build a pseudo-history)
        history = []
        # Build a simple history from current state
        # In production, this should come from a time-series database
        now = datetime.now(timezone.utc)
        history.append({
            "timestamp": now.isoformat(),
            "capital": round(capital_total, 2),
            "profit": round(profit_total, 2),
        })

        return {
            "timestamp": now.isoformat(),
            "capital_total": round(capital_total, 2),
            "capital_initial": round(capital_initial, 2),
            "profit_total": round(profit_total, 2),
            "profit_percent": round(profit_percent, 2),
            "profit_factor": round(profit_factor, 2),
            "win_rate": round(win_rate, 2),
            "total_trades": total_trades,
            "instances_count": len(instances_data),
            "by_strategy": by_strategy,
            "history": history,
        }
    except Exception:
        logger.exception("Erreur récupération performance globale")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/performance/by-pair")
async def get_performance_by_pair(request: Request, authorized: bool = Depends(verify_token)):
    """
    Performance aggregated by trading pair (BTC/EUR, ETH/EUR, etc.)
    All calculations use real instance data.

    Returns:
        pairs: List of pair-level metrics with profit factor, win rate, etc.
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        get_extended = getattr(orchestrator, 'get_instances_snapshot_extended', None)
        if get_extended:
            instances_data = get_extended()
        else:
            instances_data = orchestrator.get_instances_snapshot()

        if not instances_data:
            return {"timestamp": datetime.now(timezone.utc).isoformat(), "pairs": []}

        # Group instances by symbol
        pair_map: Dict[str, list] = {}
        for inst in instances_data:
            symbol = inst.get("symbol", inst.get("name", "UNKNOWN"))
            # Try to extract symbol from name if not available directly
            if symbol == "UNKNOWN" or "/" not in symbol:
                name = inst.get("name", "")
                # Pattern: "Auto-BTC-EUR (grid)" or "Grid BTC/EUR"
                for known in ["BTC/EUR", "ETH/EUR", "SOL/EUR", "BTC/USD",
                              "ETH/USD", "SOL/USD", "XRP/EUR", "ADA/EUR",
                              "DOT/EUR"]:
                    if known.replace("/", "-") in name or known in name:
                        symbol = known
                        break
            if symbol not in pair_map:
                pair_map[symbol] = []
            pair_map[symbol].append(inst)

        pairs_result = []
        for symbol, instances in pair_map.items():
            capital_total = sum(inst.get("capital", 0) for inst in instances)
            capital_initial = sum(
                inst.get("initial_capital", inst.get("capital", 0))
                for inst in instances
            )
            profit_total = sum(inst.get("profit", 0) for inst in instances)
            profit_percent = (profit_total / capital_initial * 100) if capital_initial > 0 else 0.0

            # Compute PF and win rate from real trades
            gross_profit = 0.0
            gross_loss = 0.0
            total_trades = 0
            winning_trades = 0
            trading_mode = "live"

            for inst in instances:
                mode = inst.get("trading_mode", "live")
                if mode in ("paper", "shadow", "dry_run"):
                    trading_mode = "paper"

                trades = inst.get("trades_history", [])
                for trade in trades:
                    pnl = trade.get("profit", 0) or 0
                    total_trades += 1
                    if pnl > 0:
                        gross_profit += pnl
                        winning_trades += 1
                    elif pnl < 0:
                        gross_loss += abs(pnl)

            # Fallback to win/loss counts
            if total_trades == 0:
                for inst in instances:
                    wc = inst.get("win_count", 0)
                    lc = inst.get("loss_count", 0)
                    total_trades += wc + lc
                    winning_trades += wc

            pf = (gross_profit / gross_loss) if gross_loss > 0 else (
                999.99 if gross_profit > 0 else 0.0
            )
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

            # Max drawdown across instances in this pair
            max_dd = max(
                (inst.get("max_drawdown", 0) for inst in instances),
                default=0.0,
            )

            pairs_result.append({
                "symbol": symbol,
                "instances_count": len(instances),
                "capital_total": round(capital_total, 2),
                "capital_initial": round(capital_initial, 2),
                "profit_total": round(profit_total, 2),
                "profit_percent": round(profit_percent, 2),
                "profit_factor": round(pf, 2),
                "win_rate": round(win_rate, 2),
                "total_trades": total_trades,
                "max_drawdown": round(max_dd * 100, 2),
                "status": trading_mode,
                "instances": [
                    {
                        "id": inst.get("id"),
                        "name": inst.get("name"),
                        "capital": round(inst.get("capital", 0), 2),
                        "profit": round(inst.get("profit", 0), 2),
                        "strategy": inst.get("strategy", "unknown"),
                        "status": inst.get("status", "unknown"),
                        "warmup": inst.get("warmup", {}),
                        "blocked_reasons": inst.get("blocked_reasons", []),
                    }
                    for inst in instances
                ],
            })

        # Sort by profit_total descending
        pairs_result.sort(key=lambda p: p["profit_total"], reverse=True)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pairs": pairs_result,
        }
    except Exception:
        logger.exception("Erreur récupération performance par paire")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/paper-trading/summary")
async def get_paper_trading_summary(request: Request, authorized: bool = Depends(verify_token)):
    """
    Summary of paper trading instances.
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        import os
        instances_data = orchestrator.get_instances_snapshot()
        
        # Check global paper trading mode
        is_paper_mode = os.getenv('PAPER_TRADING', 'false').lower() == 'true'
        
        # Count instances
        total_instances = len(instances_data)
        
        # In paper mode, all instances are considered paper
        # In live mode, all instances are considered live
        if is_paper_mode:
            paper_count = total_instances
            live_count = 0
        else:
            paper_count = 0
            live_count = total_instances
        
        # Build pair map
        pair_map = {}
        for inst in instances_data:
            # Try to determine symbol from strategy or name
            symbol = "BTC/EUR"  # Default
            strategy = inst.get("strategy", "").lower()
            name = inst.get("name", "").lower()
            
            if "btc" in strategy or "btc" in name or "bitcoin" in name:
                symbol = "BTC/EUR"
            elif "eth" in strategy or "eth" in name:
                symbol = "ETH/EUR"
            elif "sol" in strategy or "sol" in name:
                symbol = "SOL/EUR"
            
            if symbol not in pair_map:
                pair_map[symbol] = []
            pair_map[symbol].append(inst)

        # Group by symbol
        by_pair = []
        pairs_tested = len(pair_map)
        for symbol, instances in pair_map.items():
            profits_pct = []
            total_trades = 0
            winning_trades = 0
            gross_profit = 0.0
            gross_loss = 0.0

            for inst in instances:
                initial = inst.get("initial_capital", inst.get("capital", 0))
                profit = inst.get("profit", 0)
                if initial > 0:
                    profits_pct.append(profit / initial * 100)

                trades = inst.get("trades_history", [])
                for trade in trades:
                    pnl = trade.get("profit", 0) or 0
                    total_trades += 1
                    if pnl > 0:
                        gross_profit += pnl
                        winning_trades += 1
                    elif pnl < 0:
                        gross_loss += abs(pnl)

                # Fallback
                if not trades:
                    wc = inst.get("win_count", 0)
                    lc = inst.get("loss_count", 0)
                    total_trades += wc + lc
                    winning_trades += wc

            avg_profit_pct = (sum(profits_pct) / len(profits_pct)) if profits_pct else 0.0
            pair_pf = (gross_profit / gross_loss) if gross_loss > 0 else (
                999.99 if gross_profit > 0 else 0.0
            )
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

            # Recommendation logic (REAL)
            if pair_pf > 1.5 and win_rate > 55 and total_trades >= 20:
                recommendation = "promote_to_live"
            elif pair_pf > 1.0 and total_trades < 20:
                recommendation = "continue_paper"
            elif pair_pf <= 1.0 and total_trades >= 10:
                recommendation = "stop"
            else:
                recommendation = "continue_paper"

            by_pair.append({
                "symbol": symbol,
                "instance_count": len(instances),
                "total_trades": total_trades,
                "avg_profit_percent": round(avg_profit_pct, 2),
                "avg_pf": round(pair_pf, 2),
                "win_rate": round(win_rate, 2),
                "recommendation": recommendation,
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_instances": paper_count if is_paper_mode else live_count,
            "paper_instances": paper_count,
            "is_paper_mode": is_paper_mode,
            "live_instances": live_count,
            "pairs_tested": pairs_tested,
            "by_pair": by_pair,
        }
    except Exception:
        logger.exception("Erreur récupération résumé paper trading")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/rebalance/status")
async def get_rebalance_status(request: Request, authorized: bool = Depends(verify_token)):
    """Status of the auto-rebalance manager."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        rebalance_mgr = getattr(orchestrator, 'rebalance_manager', None)
        if not rebalance_mgr:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "enabled": False,
                "message": "RebalanceManager non initialisé",
            }
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **rebalance_mgr.get_status(),
        }
    except Exception:
        logger.exception("Erreur récupération statut rebalance")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/system")
async def get_system_metrics(authorized: bool = Depends(verify_token)):
    """
    Retourne les métriques système (CPU, RAM, Disk).
    """
    try:
        import psutil
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # RAM
        mem = psutil.virtual_memory()
        
        # Disk
        disk = psutil.disk_usage('/')
        
        # Déterminer le statut
        def get_status(percent):
            if percent < 70:
                return "healthy"
            elif percent < 85:
                return "warning"
            else:
                return "critical"
        
        return {
            "cpu": {
                "percent": round(cpu_percent, 1),
                "status": get_status(cpu_percent)
            },
            "memory": {
                "percent": round(mem.percent, 1),
                "used_gb": round(mem.used / (1024**3), 2),
                "total_gb": round(mem.total / (1024**3), 2),
                "status": get_status(mem.percent)
            },
            "disk": {
                "percent": round(disk.percent, 1),
                "used_gb": round(disk.used / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "status": get_status(disk.percent)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception:
        logger.exception("Erreur lors de la récupération des métriques système")
        raise HTTPException(status_code=500, detail="Erreur interne")

class DashboardServer:
    """Serveur Dashboard intégré au bot - CORRECTION: graceful shutdown"""
    
    def __init__(self, host: str | None = None, port: int = 8080):
        # CORRECTION: Bind 0.0.0.0 en Docker ou si DASHBOARD_HOST défini
        if host is not None:
            self.host = host
        elif os.getenv('DASHBOARD_HOST'):
            self.host = os.getenv('DASHBOARD_HOST')
        elif os.getenv('ENV') == 'docker':
            self.host = "0.0.0.0"
        else:
            self.host = "127.0.0.1"
        self.port = int(os.getenv('DASHBOARD_PORT', str(port)))
        self.server = None
        self.uvicorn_server = None
        
    def start(self, orchestrator):
        """Démarre le serveur dans un thread séparé"""
        # CORRECTION: Utilise app.state au lieu de global
        app.state.orchestrator = orchestrator
        
        def run_server():
            # SEC-02: HTTPS support via env-configured SSL cert/key
            ssl_certfile = os.getenv('DASHBOARD_SSL_CERT')
            ssl_keyfile = os.getenv('DASHBOARD_SSL_KEY')
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="info",
                loop="asyncio",
                ssl_certfile=ssl_certfile,
                ssl_keyfile=ssl_keyfile,
            )
            self.uvicorn_server = uvicorn.Server(config)
            self.uvicorn_server.run()

        self.server = threading.Thread(target=run_server)
        self.server.start()
        ssl_certfile = os.getenv('DASHBOARD_SSL_CERT')
        scheme = "https" if ssl_certfile else "http"
        logger.info(f"Dashboard API demarré sur {scheme}://{self.host}:{self.port}")
        if ssl_certfile:
            logger.info("HTTPS active")
        else:
            logger.warning("Dashboard en HTTP (non chiffre)")
        
        if os.getenv('DASHBOARD_API_TOKEN'):
            logger.info("🔒 Authentification activée (token configuré)")
        else:
            logger.warning("⚠️  Authentification désactivée (mode développement)")
    
    def stop(self):
        """CORRECTION: Arrêt propre du serveur"""
        logger.info("🛑 Arrêt Dashboard API...")
        if self.uvicorn_server:
            # CORRECTION: Signal d'arrêt propre à uvicorn
            self.uvicorn_server.should_exit = True
        if self.server:
            self.server.join(timeout=5.0)
        logger.info("✅ Dashboard API arrêté")

# Pour tests standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # CORRECTION: Bind localhost par défaut
    uvicorn.run(app, host="127.0.0.1", port=8080)

# Serve static files from React build (MUST be last to not override API routes)
static_dir = os.getenv("DASHBOARD_STATIC_DIR", "/app/dashboard/dist")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
