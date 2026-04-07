import re

with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'r') as f:
    content = f.read()

# Find the paper-trading/summary endpoint and fix it
old_code = '''        # Filter paper/shadow instances
        paper_instances = []
        live_instances = []
        for inst in instances_data:
            mode = inst.get("trading_mode", "live")
            if mode in ("paper", "shadow", "dry_run"):
                paper_instances.append(inst)
            else:
                live_instances.append(inst)

        # If no explicit paper mode set, treat ALL instances as live
        # and return a summary that reflects the real state
        all_instances = paper_instances if paper_instances else instances_data'''

new_code = '''        # Check global paper trading mode from environment
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

if old_code in content:
    content = content.replace(old_code, new_code)
    print('✅ Correction appliquée: mode paper détecté depuis env PAPER_TRADING')
else:
    print('⚠️ Pattern non trouvé, recherche alternative...')

# Also fix symbol detection
old_symbol = '''            if symbol == "UNKNOWN":
                name = inst.get("name", "")
                for known in ["BTC/EUR", "ETH/EUR", "SOL/EUR", "BTC/USD",
                              "ETH/USD", "SOL/USD", "XRP/EUR"]:
                    if known.replace("/", "-") in name or known in name:
                        symbol = known
                        break'''

new_symbol = '''            if symbol == "UNKNOWN" or symbol == "XXBTZEUR":
                name = inst.get("name", "")
                config = inst.get("config", {})
                # Try to get symbol from config first
                if config and "symbol" in config:
                    sym = config["symbol"]
                    if "BTC" in sym or "XBT" in sym:
                        symbol = "BTC/EUR"
                    elif "ETH" in sym:
                        symbol = "ETH/EUR"
                    elif "SOL" in sym:
                        symbol = "SOL/EUR"
                # Fallback to name parsing
                if symbol == "UNKNOWN":
                    for known in ["BTC/EUR", "ETH/EUR", "SOL/EUR", "BTC/USD",
                                  "ETH/USD", "SOL/USD", "XRP/EUR"]:
                        if known.replace("/", "-") in name or known in name:
                            symbol = known
                            break
                # Default for BTC if still unknown
                if symbol == "UNKNOWN" and ("BTC" in name or "bitcoin" in name.lower()):
                    symbol = "BTC/EUR"'''

if old_symbol in content:
    content = content.replace(old_symbol, new_symbol)
    print('✅ Correction appliquée: meilleure détection des paires')
else:
    print('⚠️ Pattern symbol non trouvé')

with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'w') as f:
    f.write(content)
