# src/autobot/trading.py
# REAL_TRADE
import uuid
from autobot.risk_manager import calculate_position_size

def execute_trade(symbol: str, side: str, amount: float) -> str:
    """
    Placeholder pour passer un ordre via CCXT.
    Calcule d'abord la taille réelle à trader via risk_manager.
    """
    # Ici on simule un capital fixe ; à remplacer par ton wallet réel.
    balance = 1000.0
    # stop_loss fictif pour le calcul de la position
    stop_loss = 0.05
    size = calculate_position_size(balance, 0.01, stop_loss)
    # code réel CCXT :
    # exchange = ccxt.binance({'apiKey': ..., 'secret': ...})
    # resp = exchange.create_order(symbol, 'market', side, size)
    # return resp['id']
    return str(uuid.uuid4())
