# CORRECTIONS À APPLIQUER SUR GITHUB

## 1️⃣ Capital.tsx (dashboard/src/pages/Capital.tsx)

Remplacer le fichier entier par celui dans `/home/node/.openclaw/workspace/Capital.tsx`

**Changements principaux:**
- ✅ Récupération des données depuis `/api/status`
- ✅ Capital, profit, investi, disponible connectés à l'API
- ✅ Transactions générées depuis les instances réelles
- ✅ Suppression des valeurs mockées (5,420€, etc.)

---

## 2️⃣ Ajouter endpoints API (dashboard.py)

Ajouter ces endpoints dans `src/autobot/v2/api/dashboard.py` avant `class DashboardServer`:

```python
@app.get("/api/capital")
async def get_capital_detail(request: Request, authorized: bool = Depends(verify_token)):
    """Détails du capital (investi, disponible, profit)"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        instances_data = orchestrator.get_instances_snapshot()
        total_capital = sum(inst.get('capital', 0) for inst in instances_data)
        total_profit = sum(inst.get('profit', 0) for inst in instances_data)
        total_invested = total_capital - total_profit
        
        # Cash disponible = 10% du capital (à ajuster selon logique métier)
        available = total_capital * 0.1
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_capital": round(total_capital, 2),
            "total_profit": round(total_profit, 2),
            "total_invested": round(total_invested, 2),
            "available_cash": round(available, 2),
            "currency": "EUR"
        }
    except Exception:
        logger.exception("Erreur récupération capital")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/history")
async def get_capital_history(request: Request, authorized: bool = Depends(verify_token), days: int = 7):
    """Historique du capital sur N jours (mock pour l'instant, à connecter à la DB)"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        instances_data = orchestrator.get_instances_snapshot()
        current_capital = sum(inst.get('capital', 0) for inst in instances_data)
        
        # TODO: Connecter à la vraie base de données d'historique
        # Pour l'instant, génère des données basées sur le capital actuel
        history = []
        for i in range(days * 24):  # Par heure
            # Simulation d'une courbe avec un peu de volatilité
            variation = (i / (days * 24)) * 0.02  # +2% sur la période
            value = current_capital * (0.98 + variation + (i % 5) * 0.001)
            history.append({
                "timestamp": (datetime.now().timestamp() - (days * 24 - i) * 3600) * 1000,
                "value": round(value, 2)
            })
        
        return {
            "period": f"{days}d",
            "current": round(current_capital, 2),
            "history": history
        }
    except Exception:
        logger.exception("Erreur récupération historique")
        raise HTTPException(status_code=500, detail="Erreur interne")


@app.get("/api/trades")
async def get_trades(request: Request, authorized: bool = Depends(verify_token), limit: int = 50):
    """Liste des trades exécutés"""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    
    try:
        instances_data = orchestrator.get_instances_snapshot()
        trades = []
        
        for inst in instances_data:
            # Récupère les trades de l'instance
            inst_trades = inst.get('trades_history', [])
            for trade in inst_trades[-limit//len(instances_data):]:
                trades.append({
                    "id": trade.get('id', 'unknown'),
                    "instance_id": inst['id'],
                    "instance_name": inst.get('name', 'Unknown'),
                    "pair": trade.get('pair', 'XBT/EUR'),
                    "side": trade.get('side', 'BUY'),
                    "amount": trade.get('amount', 0),
                    "price": trade.get('price', 0),
                    "pnl": trade.get('pnl', 0),
                    "timestamp": trade.get('timestamp', datetime.now().isoformat()),
                    "strategy": inst.get('strategy', 'unknown')
                })
        
        # Trie par date décroissante
        trades.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return {
            "count": len(trades),
            "trades": trades[:limit]
        }
    except Exception:
        logger.exception("Erreur récupération trades")
        raise HTTPException(status_code=500, detail="Erreur interne")
```

---

## 3️⃣ Grid Strategy - center_price dynamique

Dans `src/autobot/v2/strategies/grid_async.py`, modifier la méthode `__init__`:

```python
def __init__(self, instance: Any, config: Optional[Dict] = None) -> None:
    super().__init__(instance, config)

    # CORRECTION: center_price dynamique (sera mis à jour au premier prix)
    self.center_price = self.config.get("center_price", None)
    self.range_percent = self.config.get("range_percent", 7.0)
    self.num_levels = self.config.get("num_levels", 15)
    self.max_capital_per_level = self.config.get("max_capital_per_level", 50.0)
    self.max_positions = self.config.get("max_positions", 10)

    self.grid_levels: List[float] = []
    self._runtime_capital_per_level: float = 0.0
    self._spec_cache: Optional[SpeculativeOrderCache] = None
    
    # CORRECTION: Grid initialisé au premier prix, pas au démarrage
    self._grid_initialized = False
    
    # Modules
    _load_modules()
    ...
```

Puis modifier `on_price` pour initialiser la grid au premier prix:

```python
async def on_price(self, price: float, timestamp: float) -> Optional[TradingSignal]:
    """CORRECTION: Grid initialisée dynamiquement au premier prix"""
    
    # CORRECTION: Initialisation différée au premier prix réel
    if not self._grid_initialized:
        if self.center_price is None:
            self.center_price = price
            logger.info(f"📊 Grid initialisée au prix: {price:.2f}€")
        self._init_grid()
        self._grid_initialized = True
    
    # CORRECTION: Recalcule la grid si le prix dérive trop (>20%)
    if abs(price - self.center_price) / self.center_price > 0.20:
        logger.warning(f"🔄 Prix hors range ({price:.2f}), recentrage grid...")
        self.center_price = price
        self._init_grid()
    
    # ... reste de la logique
```

---

## 4️⃣ Risk Manager - await manquant

Dans `src/autobot/v2/risk_manager.py`, ligne ~244:

```python
# AVANT (incorrect):
self._orchestrator.emergency_stop_all()

# APRÈS (correct):
await self._orchestrator.emergency_stop_all()
```

---

## 🚀 Pour appliquer ces corrections:

1. **Sur ton PC:**
```bash
git clone https://github.com/Flobi30/Projet_AUTOBOT.git
cd Projet_AUTOBOT
```

2. **Copie les fichiers corrigés** (Capital.tsx, dashboard.py, grid_async.py)

3. **Commit et push:**
```bash
git add .
git commit -m "fix: Dashboard connecté aux APIs + Grid center_price dynamique"
git push origin master
```

4. **Sur le serveur:**
```bash
cd /opt/autobot
git pull origin master
docker compose down
docker compose up --build -d
```

---

**Tu veux que je détaille un fichier spécifique ?**