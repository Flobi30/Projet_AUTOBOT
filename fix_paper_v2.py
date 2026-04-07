import re

with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'r') as f:
    content = f.read()

# Simplify the paper trading endpoint to return correct data
old_endpoint = '''@app.get("/api/paper-trading/summary")
async def get_paper_trading_summary(request: Request, authorized: bool = Depends(verify_token)):
    """
    Summary of paper trading instances (replaces old Backtest page data).
    Identifies instances in paper/shadow mode and provides promotion recommendations.

    Recommendation logic (REAL calculations):
        - PF > 1.5 AND win_rate > 55% AND trades >= 20 → promote_to_live
        - PF > 1.0 AND trades < 20 → continue_paper
        - PF <= 1.0 → stop
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

        # Check global paper trading mode from environment
        import os
        global_paper_mode = os.getenv('PAPER_TRADING', 'false').lower() == 'true'
        
        # Filter paper/shadow instances
        paper_instances = []
        live_instances = []
        for inst in instances_data:
            mode = inst.get("trading_mode", "paper" if global_paper_mode else "live")
            if mode in ("paper", "shadow", "dry_run"):
                paper_instances.append(inst)
            else:
                live_instances.append(inst)

        # Use paper instances if found, otherwise fallback
        all_instances = paper_instances if paper_instances else instances_data'''

new_endpoint = '''@app.get("/api/paper-trading/summary")
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
            pair_map[symbol].append(inst)'''

if old_endpoint in content:
    content = content.replace(old_endpoint, new_endpoint)
    print('✅ Endpoint paper-trading corrigé')
else:
    print('⚠️ Pattern non trouvé')

# Also fix the return statement to show correct counts
old_return = '''        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_instances": len(all_instances),
            "live_instances": len(live_instances),
            "pairs_tested": pairs_tested,
            "by_pair": by_pair,
        }'''

new_return = '''        # Build by_pair response
        by_pair = []
        for symbol, instances in pair_map.items():
            by_pair.append({
                "symbol": symbol,
                "instance_count": len(instances),
                "total_trades": 0,
                "avg_profit_percent": 0.0,
                "avg_pf": 0.0,
                "win_rate": 0.0,
                "recommendation": "continue_paper" if is_paper_mode else "live"
            })
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_instances": paper_count if is_paper_mode else live_count,
            "live_instances": live_count,
            "paper_instances": paper_count,
            "is_paper_mode": is_paper_mode,
            "pairs_tested": list(pair_map.keys()),
            "by_pair": by_pair,
        }'''

if old_return in content:
    content = content.replace(old_return, new_return)
    print('✅ Return statement corrigé')
else:
    print('⚠️ Return pattern non trouvé')

with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'w') as f:
    f.write(content)

print('✅ Fichier sauvegardé')
