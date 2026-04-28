"""
FastAPI Dashboard Server - Expose les données du bot en temps réel
CORRECTIONS: Auth, thread-safety, graceful shutdown, error handling
"""

import logging
import os
import hmac
import hashlib
import time
import threading
import inspect
import heapq
import sqlite3
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
DASHBOARD_SESSION_COOKIE = "autobot_dashboard_session"


def _dashboard_session_value(expected_token: str) -> str:
    return hmac.new(
        expected_token.strip().encode("utf-8"),
        b"autobot-dashboard-session-v1",
        hashlib.sha256,
    ).hexdigest()



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


def _round_balances(balances: Any) -> Dict[str, float]:
    if not isinstance(balances, dict):
        return {}
    result: Dict[str, float] = {}
    for asset, value in balances.items():
        try:
            result[str(asset)] = round(float(value), 8)
        except (TypeError, ValueError):
            continue
    return result


def _infer_symbol_from_instance(inst: Dict[str, Any]) -> str:
    symbol = str(inst.get("symbol") or inst.get("pair") or "").strip()
    if symbol:
        return symbol
    haystack = f"{inst.get('name', '')} {inst.get('strategy', '')}".upper()
    known_symbols = {
        "BTC": "BTC/EUR",
        "XBT": "BTC/EUR",
        "ETH": "ETH/EUR",
        "SOL": "SOL/EUR",
        "XRP": "XRP/EUR",
        "ADA": "ADA/EUR",
        "DOT": "DOT/EUR",
    }
    for token, normalized in known_symbols.items():
        if token in haystack:
            return normalized
    return "UNKNOWN"


def _sqlite_health(db_path: Any, required_tables: List[str]) -> Dict[str, Any]:
    path = str(db_path) if db_path else ""
    result: Dict[str, Any] = {
        "path": path,
        "exists": bool(path and os.path.exists(path)),
        "accessible": False,
        "tables": {},
    }
    if not result["exists"]:
        result["status"] = "missing"
        return result
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for table in required_tables:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                table_info = {"exists": bool(row)}
                if row:
                    table_info["rows"] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                result["tables"][table] = table_info
            result["accessible"] = True
            result["status"] = "ok"
        finally:
            conn.close()
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:240]
    return result


def _latest_event(instances: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    latest: Optional[Dict[str, Any]] = None
    latest_ts = ""
    for inst in instances:
        event = inst.get(key)
        if not isinstance(event, dict):
            continue
        ts = str(event.get("timestamp") or "")
        if latest is None or ts > latest_ts:
            latest = {
                **event,
                "instance_id": event.get("instance_id") or inst.get("id"),
                "instance_name": inst.get("name"),
                "symbol": event.get("symbol") or inst.get("symbol") or _infer_symbol_from_instance(inst),
            }
            latest_ts = ts
    return latest


def _event_timestamp(event: Optional[Dict[str, Any]]) -> str:
    if not isinstance(event, dict):
        return ""
    return str(event.get("timestamp") or event.get("created_at") or "")


def _event_is_at_least(event: Optional[Dict[str, Any]], reference: Optional[Dict[str, Any]]) -> bool:
    event_ts = _event_timestamp(event)
    reference_ts = _event_timestamp(reference)
    return bool(event_ts and (not reference_ts or event_ts >= reference_ts))


def _collect_runtime_events(instances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for inst in instances:
        for event in inst.get("runtime_events", []) or []:
            if not isinstance(event, dict):
                continue
            events.append({
                **event,
                "instance_id": event.get("instance_id") or inst.get("id"),
                "instance_name": inst.get("name"),
                "symbol": event.get("symbol") or inst.get("symbol") or _infer_symbol_from_instance(inst),
            })
    events.sort(key=lambda item: _event_timestamp(item), reverse=True)
    return events


def _cost_edge_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    edge = event.get("edge_context") if isinstance(event.get("edge_context"), dict) else {}
    opportunity = event.get("opportunity") if isinstance(event.get("opportunity"), dict) else {}
    atr_pct = event.get("atr_pct")
    atr_bps = opportunity.get("atr_bps")
    if atr_bps is None:
        try:
            atr_bps = float(atr_pct) * 10000.0 if atr_pct is not None else None
        except (TypeError, ValueError):
            atr_bps = None
    return {
        "timestamp": event.get("timestamp"),
        "instance_id": event.get("instance_id"),
        "instance_name": event.get("instance_name"),
        "symbol": event.get("symbol"),
        "signal": event.get("side"),
        "signal_reason": event.get("signal_reason"),
        "price": event.get("signal_price"),
        "status": "rejected" if str(event.get("event", "")).endswith("rejected") else "accepted",
        "event": event.get("event"),
        "reason": event.get("reason"),
        "gross_edge_bps": event.get("gross_edge_bps", edge.get("expected_move_bps")),
        "cost_bps": event.get("cost_bps", edge.get("total_cost_bps")),
        "fee_bps": edge.get("estimated_fee_bps"),
        "spread_bps": edge.get("spread_bps"),
        "slippage_bps": edge.get("estimated_slippage_bps"),
        "latency_buffer_bps": 0.0,
        "risk_buffer_bps": edge.get("volatility_component_bps"),
        "atr_pct": atr_pct,
        "atr_bps": atr_bps,
        "observed_cost_buffer_bps": edge.get("observed_cost_buffer_bps"),
        "net_edge_bps": event.get("net_edge_bps", edge.get("net_edge_bps")),
        "min_edge_bps": event.get("min_edge_bps", edge.get("adaptive_min_edge_bps")),
        "gross_required_bps": event.get("gross_required_bps", edge.get("gross_required_bps")),
        "edge_shortfall_bps": event.get("edge_shortfall_bps", edge.get("edge_shortfall_bps")),
        "blocking_condition": event.get("blocking_condition"),
        "opportunity_score": opportunity.get("score"),
        "opportunity_status": opportunity.get("status"),
        "opportunity_reason": opportunity.get("reason"),
        "opportunity_blockers": opportunity.get("blockers"),
        "profile": (event.get("risk_params") or {}).get("cost_edge_profile"),
        "paper_test": event.get("signal_reason") == "paper_test_controlled_debug",
    }


def _latest_filled_paper_trade(db_path: Any) -> tuple[Optional[Dict[str, Any]], int]:
    path = str(db_path) if db_path else ""
    if not path or not os.path.exists(path):
        return None, 0
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            count = int(conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'filled'"
            ).fetchone()[0])
            row = conn.execute(
                """
                SELECT txid, symbol, side, volume, price, fees, timestamp, status
                FROM trades
                WHERE status = 'filled'
                ORDER BY timestamp DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None, count
            return {
                "txid": row[0],
                "symbol": row[1],
                "side": row[2],
                "volume": row[3],
                "price": row[4],
                "fees": row[5],
                "timestamp": row[6],
                "status": row[7],
                "source": "paper_trades_db",
            }, count
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Latest filled paper trade unavailable: %s", exc)
        return None, 0


def _paper_symbol_key(symbol: Any) -> str:
    raw = str(symbol or "").replace("/", "").upper()
    if raw == "XETHZEUR":
        return "ETHEUR"
    if raw in {"XXBTZEUR", "XBTZEUR"}:
        return "BTCEUR"
    return raw


def _filled_paper_trade_counts_by_symbol(db_path: Any) -> Dict[str, int]:
    path = str(db_path) if db_path else ""
    if not path or not os.path.exists(path):
        return {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                """
                SELECT symbol, COUNT(*)
                FROM trades
                WHERE status = 'filled'
                GROUP BY symbol
                """
            ).fetchall()
            return {_paper_symbol_key(row[0]): int(row[1]) for row in rows}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Paper trade counts unavailable: %s", exc)
        return {}


def _trading_pipeline_debug(
    *,
    instances_data: List[Dict[str, Any]],
    last_trade: Optional[Dict[str, Any]],
    trade_count: int,
    paper_mode: bool,
    decision_limit: int = 20,
) -> Dict[str, Any]:
    last_market_tick = _latest_event(instances_data, "last_market_tick")
    last_signal = _latest_event(instances_data, "last_signal")
    last_decision = _latest_event(instances_data, "last_decision")
    last_order = _latest_event(instances_data, "last_order")
    runtime_events = _collect_runtime_events(instances_data)
    cost_edge_decisions = [
        _cost_edge_event_summary(event)
        for event in runtime_events
        if event.get("reason") == "cost_guard" or event.get("event") in {"buy_rejected", "buy_accepted"}
    ]
    natural_cost_edge_rejections = [
        event for event in cost_edge_decisions
        if event.get("status") == "rejected" and not event.get("paper_test")
    ]

    status = "waiting_for_signal"
    reason = "no_signal_generated"
    blocking_condition: Optional[str] = None
    execution_reached = False

    if last_signal is None:
        warmup_or_blocked = [
            {
                "id": inst.get("id"),
                "name": inst.get("name"),
                "symbol": inst.get("symbol") or _infer_symbol_from_instance(inst),
                "warmup": inst.get("warmup", {}),
                "blocked_reasons": inst.get("blocked_reasons", []),
            }
            for inst in instances_data
            if (inst.get("warmup") or {}).get("active") or inst.get("blocked_reasons")
        ]
        if warmup_or_blocked:
            status = "blocked_before_signal"
            reason = "warmup_or_strategy_block"
            blocking_condition = ", ".join(sorted({
                str(reason)
                for inst in warmup_or_blocked
                for reason in ((inst.get("blocked_reasons") or []) + ((inst.get("warmup") or {}).get("blocked_reasons") or []))
            })) or "warmup_or_strategy_block"
    elif last_order is not None and _event_is_at_least(last_order, last_signal):
        execution_reached = True
        if str(last_order.get("event")) == "order_filled":
            status = "executed"
            reason = "paper_order_filled" if paper_mode else "order_filled"
        else:
            status = "execution_failed"
            reason = str(last_order.get("reason") or last_order.get("error") or last_order.get("event") or "order_not_filled")
            blocking_condition = reason
    elif last_decision is not None and _event_is_at_least(last_decision, last_signal):
        decision_event = str(last_decision.get("event") or "")
        decision_reason = str(last_decision.get("reason") or "decision_recorded")
        if "reject" in decision_event or "ignored" in decision_event:
            status = "rejected"
            reason = decision_reason
            blocking_condition = str(
                last_decision.get("blocking_condition")
                or last_decision.get("message")
                or decision_reason
            )
        else:
            status = "accepted_pending_execution"
            reason = decision_reason
    else:
        status = "signal_seen_no_decision"
        reason = "signal_received_without_later_decision"

    if status != "executed" and last_trade is not None and trade_count > 0:
        # A previous paper trade exists, but it is not linked to the latest signal.
        previous_trade = last_trade
    else:
        previous_trade = None

    return {
        "pipeline": {
            "market_data": {
                "seen": last_market_tick is not None,
                "last_tick": last_market_tick,
            },
            "signal": {
                "generated": last_signal is not None,
                "last_signal": last_signal,
            },
            "decision": {
                "status": status,
                "last_decision": last_decision,
                "reason": reason,
                "blocking_condition": blocking_condition,
            },
            "execution": {
                "reached": execution_reached,
                "last_order": last_order,
            },
            "paper_trade": {
                "recorded": bool(last_trade),
                "filled_trade_count": trade_count,
                "last_trade": last_trade,
                "previous_trade_not_linked_to_latest_signal": previous_trade,
            },
        },
        "status": status,
        "reason": reason,
        "blocking_condition": blocking_condition,
        "last_signal": last_signal,
        "last_decision": last_decision,
        "last_order": last_order,
        "last_trade": last_trade,
        "cost_edge_model": {
            "formula": "gross_edge_bps - (spread_bps + fee_bps + slippage_bps) = net_edge_bps; pass if net_edge_bps >= min_edge_bps",
            "latency": "hard_filter_only",
            "risk_buffer": "included in min_edge_bps via volatility_component_bps and configured min_edge_bps",
            "recent_decisions": cost_edge_decisions[:decision_limit],
            "recent_natural_rejections": natural_cost_edge_rejections[:decision_limit],
        },
    }


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

def verify_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
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

    if expected_token:
        configured_token = expected_token.strip()
        session_cookie = request.cookies.get(DASHBOARD_SESSION_COOKIE, "").strip()
        if session_cookie and hmac.compare_digest(
            session_cookie,
            _dashboard_session_value(configured_token),
        ):
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

class PaperTestSignalRequest(BaseModel):
    confirmation: str
    symbol: Optional[str] = None
    notional_eur: Optional[float] = None

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


@app.middleware("http")
async def attach_dashboard_session_cookie(request: Request, call_next):
    response = await call_next(request)
    token = os.getenv("DASHBOARD_API_TOKEN", "").strip()
    if (
        token
        and request.method == "GET"
        and not request.url.path.startswith("/api")
        and request.url.path != "/health"
    ):
        response.set_cookie(
            DASHBOARD_SESSION_COOKIE,
            _dashboard_session_value(token),
            max_age=12 * 60 * 60,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return response


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


@app.get("/api/opportunities")
async def get_opportunities(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Runtime opportunity scoring from real signal/cost traces."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        from ..opportunity_scoring import OpportunityScorer

        status = orchestrator.get_status()
        instances = orchestrator.get_instances_snapshot()
        capital_snapshot = status.get("capital") or {}
        paper_mode = bool(getattr(orchestrator, "paper_mode", capital_snapshot.get("paper_mode", False)))
        if capital_snapshot.get("source_status") == "ok":
            total_capital = float(capital_snapshot.get("total_capital", 0.0))
        else:
            total_capital = sum(float(inst.get("capital", 0.0)) for inst in instances)

        scorer = getattr(orchestrator, "opportunity_scorer", None)
        if scorer is None:
            scorer = OpportunityScorer()
            try:
                setattr(orchestrator, "opportunity_scorer", scorer)
            except Exception:
                pass

        snapshot = scorer.build_snapshot(
            instances=instances,
            paper_mode=paper_mode,
            total_capital=total_capital,
        )
        snapshot["capital"] = {
            "total_capital": round(total_capital, 2),
            "source": capital_snapshot.get("source"),
            "source_status": capital_snapshot.get("source_status"),
        }
        snapshot["runtime"] = {
            "running": bool(status.get("running")),
            "websocket_connected": bool(status.get("websocket_connected")),
            "instance_count": int(status.get("instance_count", len(instances))),
        }
        return snapshot
    except Exception:
        logger.exception("Erreur recuperation opportunity scoring")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/colony")
async def get_colony(
    request: Request,
    authorized: bool = Depends(verify_token)
):
    """Paper-first Grid colony control plane.

    This endpoint describes how AUTOBOT would allocate logical Grid children,
    promotion gates and split gates.  It is intentionally read-only: no child is
    promoted to live and no order is placed from here.
    """
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        from ..colony_manager import ColonyManager
        from ..opportunity_scoring import OpportunityScorer

        status = orchestrator.get_status()
        instances = orchestrator.get_instances_snapshot()
        capital_snapshot = status.get("capital") or {}
        paper_mode = bool(getattr(orchestrator, "paper_mode", capital_snapshot.get("paper_mode", False)))
        total_capital = float(capital_snapshot.get("total_capital") or capital_snapshot.get("total_balance") or 0.0)
        if total_capital <= 0.0:
            total_capital = sum(float(inst.get("capital", 0.0)) for inst in instances)

        scorer = getattr(orchestrator, "opportunity_scorer", None)
        if scorer is None:
            scorer = OpportunityScorer()
            try:
                setattr(orchestrator, "opportunity_scorer", scorer)
            except Exception:
                pass

        opportunities_snapshot = scorer.build_snapshot(
            instances=instances,
            paper_mode=paper_mode,
            total_capital=total_capital,
        )
        manager = getattr(orchestrator, "colony_manager", None)
        if manager is None:
            manager = ColonyManager()
            try:
                setattr(orchestrator, "colony_manager", manager)
            except Exception:
                pass

        return manager.build_snapshot(
            opportunities=opportunities_snapshot.get("opportunities", []),
            instances=instances,
            capital=capital_snapshot,
            paper_mode=paper_mode,
        )
    except Exception:
        logger.exception("Erreur recuperation colony manager")
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
        balances = _round_balances(snapshot.get("balances", {}))
        paper_mode = bool(snapshot.get("paper_mode", False))
        timestamp = snapshot.get("timestamp", datetime.now(timezone.utc).isoformat())
        total_balance = round(float(snapshot.get("total_balance", 0.0)), 2)
        cash_balance = round(float(snapshot.get("cash_balance", 0.0)), 2)

        return {
            "timestamp": timestamp,
            "total_capital": round(float(snapshot.get("total_capital", 0.0)), 2),
            "total_balance": total_balance,
            "allocated_capital": round(float(snapshot.get("allocated_capital", 0.0)), 2),
            "reserve_cash": round(float(snapshot.get("reserve_cash", 0.0)), 2),
            "total_profit": round(float(snapshot.get("total_profit", 0.0)), 2),
            "total_invested": round(float(snapshot.get("total_invested", 0.0)), 2),
            "available_cash": round(float(snapshot.get("available_cash", 0.0)), 2),
            "cash_balance": cash_balance,
            "open_position_notional": round(float(snapshot.get("open_position_notional", 0.0)), 2),
            "currency": snapshot.get("currency", "EUR"),
            "paper_mode": paper_mode,
            "source": snapshot.get("source", "unknown"),
            "source_status": snapshot.get("source_status", "unknown"),
            "balances": balances,
            "paper_account": {
                "active": paper_mode,
                "total_balance": total_balance if paper_mode else None,
                "available_cash": round(float(snapshot.get("available_cash", 0.0)), 2) if paper_mode else None,
                "balances": balances if paper_mode else {},
                "message": "Capital virtuel persistant du paper trading." if paper_mode else "Paper trading inactif.",
            },
            "kraken_account": {
                "connected": (not paper_mode) and snapshot.get("source") == "kraken" and snapshot.get("source_status") == "ok",
                "total_balance": total_balance if not paper_mode else None,
                "eur_available": cash_balance if not paper_mode else None,
                "balances": balances if not paper_mode else {},
                "last_sync": timestamp if not paper_mode else None,
                "message": (
                    "Solde Kraken lu cote backend."
                    if not paper_mode
                    else "Mode paper: aucun capital reel n'est engage par AUTOBOT."
                ),
            },
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
            symbol = _infer_symbol_from_instance(inst)
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
            trading_mode = "paper" if bool(getattr(orchestrator, "paper_mode", False)) else "live"

            for inst in instances:
                mode = inst.get("trading_mode", trading_mode)
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
                        "symbol": inst.get("symbol") or _infer_symbol_from_instance(inst),
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
            symbol = _infer_symbol_from_instance(inst)
            if symbol not in pair_map:
                pair_map[symbol] = []
            pair_map[symbol].append(inst)

        executor = getattr(orchestrator, "order_executor", None)
        paper_trade_counts = (
            _filled_paper_trade_counts_by_symbol(getattr(executor, "db_path", "data/paper_trades.db"))
            if is_paper_mode else {}
        )

        # Group by symbol
        by_pair = []
        pairs_tested = len(pair_map)
        for symbol, instances in pair_map.items():
            profits_pct = []
            total_trades = 0
            winning_trades = 0
            gross_profit = 0.0
            gross_loss = 0.0
            warmup_active = 0
            blocked_reasons = set()

            for inst in instances:
                initial = inst.get("initial_capital", inst.get("capital", 0))
                profit = inst.get("profit", 0)
                if initial > 0:
                    profits_pct.append(profit / initial * 100)
                warmup = inst.get("warmup") or {}
                if warmup.get("active"):
                    warmup_active += 1
                for reason in inst.get("blocked_reasons", []) or warmup.get("blocked_reasons", []):
                    blocked_reasons.add(str(reason))

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

            paper_filled_trades = paper_trade_counts.get(_paper_symbol_key(symbol), 0)
            total_trades = max(total_trades, paper_filled_trades)

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
                "warmup_active": warmup_active,
                "blocked_reasons": sorted(blocked_reasons),
                "paper_filled_trades": paper_filled_trades,
                "trade_count_source": "paper_trades_db" if paper_filled_trades else "instance_memory",
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


@app.get("/api/runtime/trace")
async def get_runtime_trace(request: Request, authorized: bool = Depends(verify_token)):
    """Operational trace proving whether AUTOBOT is really doing work."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        status = orchestrator.get_status()
        instances_data = orchestrator.get_instances_snapshot()
        paper_mode = bool(getattr(orchestrator, "paper_mode", status.get("capital", {}).get("paper_mode", False)))
        mode = "paper" if paper_mode else "live"
        executor = getattr(orchestrator, "order_executor", None)
        persistence = getattr(orchestrator, "persistence", None)

        state_db_path = getattr(persistence, "db_path", "data/autobot_state.db")
        paper_db_path = getattr(executor, "db_path", "data/paper_trades.db")
        state_db = _sqlite_health(state_db_path, ["positions", "instance_state", "trade_ledger"])
        paper_db = _sqlite_health(paper_db_path, ["trades"]) if paper_mode else {
            "path": str(paper_db_path) if paper_db_path else "",
            "exists": False,
            "accessible": False,
            "status": "not_used_in_live_mode",
            "tables": {},
        }

        open_orders_count: Optional[int] = None
        open_orders_status = "unavailable"
        if executor is not None and hasattr(executor, "get_open_orders"):
            try:
                open_orders = await executor.get_open_orders()
                open_orders_count = len(open_orders) if isinstance(open_orders, dict) else 0
                open_orders_status = "ok"
            except Exception as exc:
                open_orders_status = "error"
                open_orders_count = None
                logger.warning("Runtime trace open orders unavailable: %s", exc)

        last_trade = None
        trade_count = 0
        if paper_db.get("accessible") and (paper_db.get("tables", {}).get("trades") or {}).get("exists"):
            last_trade, trade_count = _latest_filled_paper_trade(paper_db.get("path"))

        if last_trade is None and state_db.get("accessible") and (state_db.get("tables", {}).get("trade_ledger") or {}).get("exists"):
            trade_count = max(trade_count, int((state_db["tables"]["trade_ledger"]).get("rows", 0)))
            try:
                conn = sqlite3.connect(f"file:{state_db['path']}?mode=ro", uri=True)
                try:
                    row = conn.execute(
                        """
                        SELECT trade_id, symbol, side, volume, executed_price, fees, created_at
                        FROM trade_ledger
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ).fetchone()
                    if row:
                        last_trade = {
                            "trade_id": row[0],
                            "symbol": row[1],
                            "side": row[2],
                            "volume": row[3],
                            "price": row[4],
                            "fees": row[5],
                            "timestamp": row[6],
                            "source": "trade_ledger_db",
                        }
                finally:
                    conn.close()
            except Exception as exc:
                logger.warning("Runtime trace last ledger trade unavailable: %s", exc)

        pair_set = {_infer_symbol_from_instance(inst) for inst in instances_data}
        pair_set.discard("UNKNOWN")
        strategy_names = sorted({str(inst.get("strategy") or "unknown") for inst in instances_data})
        warmup_instances = [
            {
                "id": inst.get("id"),
                "name": inst.get("name"),
                "symbol": inst.get("symbol") or _infer_symbol_from_instance(inst),
                "warmup": inst.get("warmup", {}),
                "blocked_reasons": inst.get("blocked_reasons", []),
            }
            for inst in instances_data
            if (inst.get("warmup") or {}).get("active") or inst.get("blocked_reasons")
        ]

        recent_errors: List[Dict[str, Any]] = []
        for inst in instances_data:
            err = inst.get("last_error")
            if isinstance(err, dict):
                recent_errors.append({
                    **err,
                    "instance_id": err.get("instance_id") or inst.get("id"),
                    "instance_name": inst.get("name"),
                })
        module_diagnostics = status.get("module_diagnostics") or {}
        if isinstance(module_diagnostics, dict):
            for module_name, diag in module_diagnostics.items():
                if isinstance(diag, dict) and (diag.get("error") or diag.get("status") in {"error", "critical"}):
                    recent_errors.append({
                        "timestamp": diag.get("timestamp"),
                        "module": module_name,
                        "event": "module_diagnostic",
                        "error": str(diag.get("error") or diag.get("status"))[:240],
                    })

        last_market_tick = _latest_event(instances_data, "last_market_tick")
        if last_market_tick is None:
            priced_instances = [inst for inst in instances_data if inst.get("last_price")]
            if priced_instances:
                inst = priced_instances[-1]
                last_market_tick = {
                    "timestamp": None,
                    "instance_id": inst.get("id"),
                    "instance_name": inst.get("name"),
                    "symbol": inst.get("symbol") or _infer_symbol_from_instance(inst),
                    "price": inst.get("last_price"),
                    "source": "instance_memory_no_timestamp",
                }

        checks = [
            {"name": "backend_api", "ok": True, "status": "ok"},
            {"name": "orchestrator", "ok": bool(status.get("running")), "status": "running" if status.get("running") else "stopped"},
            {"name": "market_websocket", "ok": bool(status.get("websocket_connected")), "status": "connected" if status.get("websocket_connected") else "disconnected"},
            {"name": "state_database", "ok": bool(state_db.get("accessible")), "status": state_db.get("status")},
            {"name": "paper_database", "ok": bool(paper_db.get("accessible")) if paper_mode else True, "status": paper_db.get("status")},
            {"name": "order_executor", "ok": executor is not None, "status": type(executor).__name__ if executor is not None else "missing"},
            {"name": "strategies_imported", "ok": len(instances_data) > 0, "status": f"{len(instances_data)} strategies"},
            {"name": "market_tick_received", "ok": last_market_tick is not None, "status": "seen" if last_market_tick else "waiting"},
        ]

        critical_failed = any(not c["ok"] for c in checks if c["name"] in {"orchestrator", "market_websocket", "state_database", "order_executor"})
        if critical_failed:
            overall_status = "critical"
        elif trade_count == 0:
            overall_status = "warning"
        elif recent_errors:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        messages = []
        if trade_count == 0:
            messages.append("Bot actif mais aucune execution encore enregistree.")
        if paper_mode:
            messages.append("Mode paper: aucun capital reel n'est engage par AUTOBOT.")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "mode": mode,
            "paper_mode": paper_mode,
            "capital": status.get("capital", {}),
            "runtime": {
                "running": bool(status.get("running")),
                "websocket_connected": bool(status.get("websocket_connected")),
                "uptime_seconds": status.get("uptime_seconds"),
                "instance_count": len(instances_data),
            },
            "strategies": {
                "active_count": len(instances_data),
                "names": strategy_names,
                "pairs_watched": sorted(pair_set),
                "warmup_or_blocked": warmup_instances,
            },
            "database": {
                "state": state_db,
                "paper": paper_db,
            },
            "order_executor": {
                "class_name": type(executor).__name__ if executor is not None else None,
                "open_orders_status": open_orders_status,
                "open_orders_count": open_orders_count,
                "recorded_trades_count": trade_count,
            },
            "trace": {
                "last_market_tick": last_market_tick,
                "last_signal": _latest_event(instances_data, "last_signal"),
                "last_decision": _latest_event(instances_data, "last_decision") or status.get("last_decision"),
                "last_order": _latest_event(instances_data, "last_order"),
                "last_trade": last_trade,
                "last_error": recent_errors[-1] if recent_errors else None,
                "recent_errors": recent_errors[-10:],
            },
            "checks": checks,
            "messages": messages,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erreur runtime trace")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/trading/debug")
async def get_trading_debug(
    request: Request,
    decision_limit: int = Query(20, ge=1, le=100),
    authorized: bool = Depends(verify_token),
):
    """Explain the latest Market Data -> Signal -> Decision -> Execution state."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    try:
        status = orchestrator.get_status()
        instances_data = orchestrator.get_instances_snapshot()
        paper_mode = bool(getattr(orchestrator, "paper_mode", status.get("capital", {}).get("paper_mode", False)))
        executor = getattr(orchestrator, "order_executor", None)
        paper_db_path = getattr(executor, "db_path", "data/paper_trades.db")
        last_trade, filled_trade_count = _latest_filled_paper_trade(paper_db_path) if paper_mode else (None, 0)

        debug = _trading_pipeline_debug(
            instances_data=instances_data,
            last_trade=last_trade,
            trade_count=filled_trade_count,
            paper_mode=paper_mode,
            decision_limit=decision_limit,
        )

        per_instance = []
        for inst in instances_data:
            inst_debug = _trading_pipeline_debug(
                instances_data=[inst],
                last_trade=last_trade,
                trade_count=filled_trade_count,
                paper_mode=paper_mode,
                decision_limit=min(decision_limit, 20),
            )
            per_instance.append({
                "id": inst.get("id"),
                "name": inst.get("name"),
                "symbol": inst.get("symbol") or _infer_symbol_from_instance(inst),
                "status": inst_debug["status"],
                "reason": inst_debug["reason"],
                "blocking_condition": inst_debug["blocking_condition"],
                "warmup": inst.get("warmup", {}),
                "blocked_reasons": inst.get("blocked_reasons", []),
                "last_price": inst.get("last_price"),
                "last_signal": inst_debug["last_signal"],
                "last_decision": inst_debug["last_decision"],
                "last_order": inst_debug["last_order"],
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "overall": {
                "status": debug["status"],
                "reason": debug["reason"],
                "blocking_condition": debug["blocking_condition"],
            },
            **debug,
            "instances": per_instance,
            "paper_test_mode": {
                "enabled": os.getenv("PAPER_TEST_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                "endpoint": "/api/trading/test-paper-signal",
                "guardrails": [
                    "paper_mode_required",
                    "PaperTradingExecutor_required",
                    "auth_required",
                    "confirmation_required",
                    "small_notional_cap",
                ],
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erreur trading debug")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.post("/api/trading/test-paper-signal")
async def trigger_paper_test_signal(
    payload: PaperTestSignalRequest,
    request: Request,
    authorized: bool = Depends(verify_token),
):
    """Inject a tiny paper-only test signal through the normal signal handler."""
    if os.getenv("PAPER_TEST_TRADING_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="Mode test paper non activé")
    if payload.confirmation != "EXECUTE_PAPER_TEST":
        raise HTTPException(status_code=400, detail="Confirmation EXECUTE_PAPER_TEST requise")

    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")

    status = orchestrator.get_status()
    paper_mode = bool(getattr(orchestrator, "paper_mode", status.get("capital", {}).get("paper_mode", False)))
    executor = getattr(orchestrator, "order_executor", None)
    if not paper_mode or type(executor).__name__ != "PaperTradingExecutor":
        raise HTTPException(status_code=409, detail="Test autorisé uniquement avec PaperTradingExecutor en paper mode")

    instances = list(getattr(orchestrator, "_instances", {}).values())
    if payload.symbol:
        wanted = payload.symbol.replace("/", "").upper()
        instances = [
            inst for inst in instances
            if wanted in str(getattr(getattr(inst, "config", None), "symbol", "")).replace("/", "").upper()
        ]
    if not instances:
        raise HTTPException(status_code=404, detail="Aucune instance paper compatible")

    max_notional = min(25.0, max(1.0, float(os.getenv("PAPER_TEST_MAX_NOTIONAL_EUR", "10.0"))))
    requested_notional = payload.notional_eur if payload.notional_eur is not None else 5.0
    requested_notional = min(max_notional, max(1.0, float(requested_notional)))

    selected = None
    selected_price = 0.0
    selected_notional = requested_notional
    for inst in sorted(instances, key=lambda i: str(getattr(getattr(i, "config", None), "symbol", ""))):
        inst_status = inst.get_status() if hasattr(inst, "get_status") else {}
        price = float(inst_status.get("last_price") or 0.0)
        handler = getattr(inst, "_signal_handler", None)
        if price <= 0 or handler is None:
            continue
        min_notional = price * 0.0001 * 1.02
        if min_notional <= max_notional:
            selected = inst
            selected_price = price
            selected_notional = max(requested_notional, min_notional)
            break

    if selected is None:
        raise HTTPException(status_code=409, detail="Aucune instance avec prix courant et volume minimum paper compatible")

    from ..strategies import TradingSignal, SignalType

    handler = getattr(selected, "_signal_handler", None)
    symbol = getattr(selected.config, "symbol", payload.symbol or "UNKNOWN")
    volume = round(max(0.0001, selected_notional / selected_price), 6)
    signal = TradingSignal(
        type=SignalType.BUY,
        symbol=symbol,
        price=selected_price,
        volume=volume,
        reason="paper_test_controlled_debug",
        timestamp=datetime.now(timezone.utc),
        metadata={
            "spread_bps": 0.1,
            "expected_move_bps": 250.0,
            "fee_bps": 0.1,
            "slippage_bps": 0.1,
            "expected_slippage_bps": 0.1,
            "urgency": 0.0,
            "limit_price": selected_price,
        },
    )

    previous_last_signal_time = getattr(handler, "_last_signal_time", None)
    handler._last_signal_time = None
    try:
        await handler._on_signal(signal)
    finally:
        if getattr(handler, "_last_signal_time", None) is None:
            handler._last_signal_time = previous_last_signal_time

    instances_data = orchestrator.get_instances_snapshot()
    paper_db_path = getattr(executor, "db_path", "data/paper_trades.db")
    last_trade, filled_trade_count = _latest_filled_paper_trade(paper_db_path)
    debug = _trading_pipeline_debug(
        instances_data=instances_data,
        last_trade=last_trade,
        trade_count=filled_trade_count,
        paper_mode=True,
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triggered": True,
        "paper_mode": True,
        "instance_id": getattr(selected, "id", None),
        "symbol": symbol,
        "price": selected_price,
        "volume": volume,
        "notional_eur": round(volume * selected_price, 8),
        "result_status": debug["status"],
        "result_reason": debug["reason"],
        "debug": debug,
    }


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

    @staticmethod
    def _resolve_ssl_files() -> tuple[str | None, str | None]:
        certfile = os.getenv('DASHBOARD_SSL_CERT')
        keyfile = os.getenv('DASHBOARD_SSL_KEY')
        if not certfile and not keyfile:
            return None, None
        if not certfile or not keyfile:
            logger.warning("HTTPS dashboard disabled: cert or key is missing")
            return None, None
        if not os.path.isfile(certfile) or not os.path.isfile(keyfile):
            logger.warning("HTTPS dashboard disabled: cert/key files are absent")
            return None, None
        if not os.access(certfile, os.R_OK) or not os.access(keyfile, os.R_OK):
            logger.warning("HTTPS dashboard disabled: cert/key not readable by container user")
            return None, None
        return certfile, keyfile
        
    def start(self, orchestrator):
        """Démarre le serveur dans un thread séparé"""
        # CORRECTION: Utilise app.state au lieu de global
        app.state.orchestrator = orchestrator
        
        def run_server():
            # SEC-02: HTTPS support via env-configured SSL cert/key
            ssl_certfile, ssl_keyfile = self._resolve_ssl_files()
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
        ssl_certfile, _ = self._resolve_ssl_files()
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
