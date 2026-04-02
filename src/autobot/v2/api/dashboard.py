"""
FastAPI Dashboard Server - Expose les données du bot en temps réel
CORRECTIONS: Auth, thread-safety, graceful shutdown, error handling
"""

import logging
import os
import time
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)

# CORRECTION: Sécurité - Token Bearer pour auth
security = HTTPBearer(auto_error=False)

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Vérifie le token API.

    - En mode development (APP_ENV=development) : token facultatif.
    - En tout autre environnement : token obligatoire.
    """
    app_env = os.getenv('APP_ENV', 'production').lower()
    expected_token = os.getenv('DASHBOARD_API_TOKEN')

    # Mode development sans token configuré : accès libre
    if app_env == 'development' and not expected_token:
        return True

    # Hors development OU token configuré : authentification obligatoire
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="DASHBOARD_API_TOKEN non configuré — accès refusé en production"
        )

    if credentials.credentials != expected_token:
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

@app.get("/")
async def root():
    return {"message": "AUTOBOT V2 Dashboard API", "version": "2.0.0"}

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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
        status = orchestrator.get_status_safe()
        return GlobalStatus(
            running=status['running'],
            instance_count=status['instance_count'],
            total_capital=sum(inst['capital'] for inst in status['instances']),
            total_profit=sum(inst.get('profit', 0) for inst in status['instances']),
            websocket_connected=status['websocket_connected'],
            uptime_seconds=(datetime.now() - status['start_time']).total_seconds() if status['start_time'] else None
        )
    except Exception:
        logger.exception("Erreur récupération statut global")
        # CORRECTION: Ne pas exposer détails de l'erreur
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
                open_positions=inst['open_positions']
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
        orchestrator.stop()
        return {
            "message": "Arrêt d'urgence exécuté", 
            "timestamp": datetime.now().isoformat(),
            "status": "stopped"
        }
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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
            "timestamp": datetime.now().isoformat(),
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
