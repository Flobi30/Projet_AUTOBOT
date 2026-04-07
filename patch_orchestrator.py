import re

with open('/opt/Projet_AUTOBOT/src/autobot/v2/orchestrator_async.py', 'r') as f:
    content = f.read()

# Remplacer la création de l'order executor
old_code = '''        # Order executor (async)
        self.order_executor = get_order_executor_async(api_key, api_secret)'''

new_code = '''        # Order executor (async) — PaperTrading si PAPER_TRADING=true
        import os as _os
        self.paper_mode = _os.getenv("PAPER_TRADING", "false").lower() == "true"
        
        if self.paper_mode and PaperTradingExecutor is not None:
            initial_capital = float(_os.getenv("INITIAL_CAPITAL", "1000.0"))
            self.order_executor = PaperTradingExecutor(
                db_path="data/paper_trades.db",
                initial_capital=initial_capital,
            )
            logger.info(f"🎮 MODE PAPER TRADING (capital: {initial_capital:.0f}€)")
        else:
            self.order_executor = get_order_executor_async(api_key, api_secret)
            logger.info("🔴 MODE LIVE TRADING")'''

content = content.replace(old_code, new_code)

with open('/opt/Projet_AUTOBOT/src/autobot/v2/orchestrator_async.py', 'w') as f:
    f.write(content)

print('✅ Order executor patché')
