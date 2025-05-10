Crée un module `src/autobot/risk_manager.py` qui :
- Définit `calculate_position_size(balance: float, risk_pct: float, stop_loss: float) -> float`.
- Utilise la formule Kelly ou VaR basique : `risk_amount = balance * risk_pct`; `size = risk_amount / stop_loss`.
Dans `src/autobot/trading.py`, modifie `execute_trade()` pour qu’il :
- Appelle `from autobot.risk_manager import calculate_position_size`
- Calcule `size` avant de passer l’ordre.
Ajoute un commentaire `# REAL_RISK`.
