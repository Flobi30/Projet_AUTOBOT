"""
FastAPI Dashboard Server - Expose les données du bot en temps réel
CORRECTIONS: Auth, thread-safety, graceful shutdown, error handling
"""

import logging
import os
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
    """Vérifie le token API (si configuré)"""
    expected_token = os.getenv('DASHBOARD_API_TOKEN')
    
    # Si pas de token configuré, on laisse passer (mode dev)
    if not expected_token:
        return True
    
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")
    
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

# CORRECTION: CORS moins permissif
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # CORRECTION: Pas "*"
    allow_headers=["Content-Type", "Authorization"],  # CORRECTION: Pas "*"
)

@app.get("/")
async def root():
    return {"message": "AUTOBOT V2 Dashboard API", "version": "2.0.0"}

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

class DashboardServer:
    """Serveur Dashboard intégré au bot - CORRECTION: graceful shutdown"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8080):  # CORRECTION: 127.0.0.1 par défaut
        self.host = host
        self.port = port
        self.server = None
        self.uvicorn_server = None
        
    def start(self, orchestrator):
        """Démarre le serveur dans un thread séparé"""
        # CORRECTION: Utilise app.state au lieu de global
        app.state.orchestrator = orchestrator
        
        def run_server():
            # CORRECTION: Utilise uvicorn.Server pour shutdown propre
            config = uvicorn.Config(
                app, 
                host=self.host, 
                port=self.port, 
                log_level="info",
                loop="asyncio"
            )
            self.uvicorn_server = uvicorn.Server(config)
            self.uvicorn_server.run()
        
        self.server = threading.Thread(target=run_server)
        self.server.start()
        logger.info(f"🌐 Dashboard API démarré sur http://{self.host}:{self.port}")
        
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
