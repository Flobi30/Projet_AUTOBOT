"""
FastAPI Dashboard Server - Expose les données du bot en temps réel
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)

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

class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str

# Application FastAPI
app = FastAPI(
    title="AUTOBOT V2 Dashboard API",
    description="API pour le dashboard de monitoring du bot de trading",
    version="2.0.0"
)

# CORS pour permettre au frontend React de se connecter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Référence à l'orchestrateur (sera injectée au démarrage)
orchestrator_ref = None

def set_orchestrator(orch):
    """Injecte l'orchestrateur pour accès aux données"""
    global orchestrator_ref
    orchestrator_ref = orch
    logger.info("🔗 Orchestrateur connecté à l'API Dashboard")

@app.get("/")
async def root():
    return {"message": "AUTOBOT V2 Dashboard API", "version": "2.0.0"}

@app.get("/api/status", response_model=GlobalStatus)
async def get_global_status():
    """Retourne le statut global du bot"""
    if not orchestrator_ref:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        status = orchestrator_ref.get_status()
        return GlobalStatus(
            running=status['running'],
            instance_count=status['instance_count'],
            total_capital=sum(inst['capital'] for inst in status['instances']),
            total_profit=sum(inst.get('profit', 0) for inst in status['instances']),
            websocket_connected=status['websocket_connected'],
            uptime_seconds=(datetime.now() - status['start_time']).total_seconds() if status['start_time'] else None
        )
    except Exception as e:
        logger.exception("Erreur récupération statut global")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/instances", response_model=List[InstanceStatus])
async def get_instances():
    """Liste toutes les instances actives"""
    if not orchestrator_ref:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        instances = []
        for inst_id, instance in orchestrator_ref._instances.items():
            inst_status = instance.get_status()
            instances.append(InstanceStatus(
                id=inst_id,
                name=instance.config.name,
                capital=inst_status['current_capital'],
                profit=inst_status['total_profit'],
                status=inst_status['status'],
                strategy=instance.config.strategy,
                open_positions=len(inst_status['positions'])
            ))
        return instances
    except Exception as e:
        logger.exception("Erreur récupération instances")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/instances/{instance_id}/positions", response_model=List[PositionInfo])
async def get_instance_positions(instance_id: str):
    """Retourne les positions ouvertes d'une instance"""
    if not orchestrator_ref:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        instance = orchestrator_ref._instances.get(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance non trouvée")
        
        positions = []
        for pos_id, pos in instance._positions.items():
            current_price = instance._last_price or pos.buy_price
            pnl = (current_price - pos.buy_price) * pos.volume
            pnl_pct = (current_price - pos.buy_price) / pos.buy_price * 100
            
            positions.append(PositionInfo(
                pair=instance.config.symbol,
                side="LONG",
                size=f"{pos.volume:.6f} BTC",
                entry_price=pos.buy_price,
                current_price=current_price,
                pnl=pnl,
                pnl_percent=pnl_pct
            ))
        return positions
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur récupération positions instance {instance_id}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/emergency-stop")
async def emergency_stop():
    """Arrêt d'urgence - ferme toutes les instances"""
    if not orchestrator_ref:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        logger.warning("🚨 ARRÊT D'URGENCE demandé via Dashboard!")
        orchestrator_ref.stop()
        return {"message": "Arrêt d'urgence exécuté", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.exception("Erreur arrêt d'urgence")
        raise HTTPException(status_code=500, detail=str(e))

class DashboardServer:
    """Serveur Dashboard intégré au bot"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server = None
        
    def start(self, orchestrator):
        """Démarre le serveur dans un thread séparé"""
        set_orchestrator(orchestrator)
        
        import threading
        def run_server():
            uvicorn.run(app, host=self.host, port=self.port, log_level="info")
        
        self.server = threading.Thread(target=run_server, daemon=True)
        self.server.start()
        logger.info(f"🌐 Dashboard API démarré sur http://{self.host}:{self.port}")
    
    def stop(self):
        """Arrête le serveur"""
        logger.info("🛑 Arrêt Dashboard API...")
        # Note: uvicorn ne s'arrête pas proprement en thread daemon
        # Le processus principal doit gérer le shutdown

# Pour tests standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=8080)
