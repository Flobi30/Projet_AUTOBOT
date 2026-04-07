import psutil

@app.get("/api/system")
async def get_system_metrics(authorized: bool = Depends(verify_token)):
    """
    Retourne les métriques système (CPU, RAM, Disk).
    """
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        
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
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des métriques système: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur système: {str(e)}")
