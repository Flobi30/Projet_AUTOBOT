from fastapi import APIRouter, HTTPException
from autobot.schemas import CapitalStatus
from autobot.profit_engine import CapitalManager

router = APIRouter()

@router.get('/api/capital-status', response_model=CapitalStatus)
async def get_capital_status():
    """
    Get current capital status including deposits, withdrawals, and trading profit.
    
    Returns:
        CapitalStatus: Current capital status and metrics
    """
    try:
        capital_manager = CapitalManager()
        summary = capital_manager.get_capital_summary()
        
        return CapitalStatus(
            initial_capital=summary["initial_capital"],
            current_capital=summary["current_capital"],
            total_deposits=summary["total_deposits"],
            total_withdrawals=summary["total_withdrawals"],
            trading_profit=summary["trading_profit"],
            total_profit=summary["total_profit"],
            roi=summary["roi"],
            available_for_withdrawal=summary["available_for_withdrawal"],
            last_updated=summary["last_updated"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get capital status: {str(e)}")
