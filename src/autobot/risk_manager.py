# src/autobot/risk_manager.py
# REAL_RISK

def calculate_position_size(balance: float, risk_pct: float, stop_loss: float) -> float:
    """
    Calcule la taille de la position selon le risque défini.
    risk_amount = balance * risk_pct
    size = risk_amount / stop_loss
    """
    risk_amount = balance * risk_pct
    size = risk_amount / stop_loss
    return size
