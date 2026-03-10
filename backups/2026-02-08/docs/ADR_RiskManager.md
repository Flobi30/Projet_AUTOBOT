# 📘 ADR - Risk Manager Module

## ADR-004: Architecture Risk Management

### Contexte
Objectif 30-40% ROI mensuel requiert gestion risque drastique:
- Protection capital priorité absolue
- Drawdown contrôlé (<15%)
- Position sizing adaptatif
- Kill switches automatiques

### Décision
Architecture **Multi-couches protection**:

```
┌─────────────────────────────────────────────────────────────┐
│                    RISK MANAGER                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Position Sizing                                   │
│  ├── Kelly Criterion (fractional)                          │
│  ├── Volatility targeting                                  │
│  └── Max exposure per asset                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Portfolio Risk                                    │
│  ├── VaR (95%, 99%)                                        │
│  ├── Correlation monitoring                                  │
│  └── Beta adjustment                                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Circuit Breakers                                  │
│  ├── Daily loss limit (-5%)                                │
│  ├── Drawdown limit (-15%)                                 │
│  └── Volatility spike detector                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Emergency Stops                                   │
│  ├── Hard stop (-20% capital)                              │
│  ├── Manual override                                        │
│  └── All positions flatten                                  │
└─────────────────────────────────────────────────────────────┘
```

### Position Sizing - Kelly Criterion

```python
class KellyPositionSizer:
    """
    Kelly Criterion avec réduction conservatrice
    """
    
    def __init__(self, fraction=0.5):  # Half-Kelly par défaut
        self.fraction = fraction
        self.max_position = 0.10  # 10% max par trade
    
    def calculate(self, win_rate, avg_win, avg_loss):
        """
        Kelly % = (W * R - (1 - W)) / R
        W = win rate
        R = win/loss ratio
        """
        if avg_loss == 0:
            return 0
        
        kelly = (win_rate * (avg_win/avg_loss) - (1 - win_rate)) / (avg_win/avg_loss)
        kelly = max(0, min(kelly, 1))  # Clamp [0, 1]
        
        # Half-Kelly pour réduire volatilité
        position = kelly * self.fraction
        
        # Hard limit
        return min(position, self.max_position)
```

### VaR Calculation

```python
class VaRCalculator:
    """
    Value at Risk - Historical simulation
    """
    
    def __init__(self, lookback_days=252):
        self.lookback = lookback_days
    
    def calculate_var(self, returns, confidence=0.95):
        """
        VaR historique
        """
        return np.percentile(returns, (1 - confidence) * 100)
    
    def calculate_cvar(self, returns, confidence=0.95):
        """
        Conditional VaR (Expected Shortfall)
        """
        var = self.calculate_var(returns, confidence)
        return returns[returns <= var].mean()
```

### Circuit Breakers Financiers

```python
class FinancialCircuitBreakers:
    """
    Protection contre drawdowns excessifs
    """
    
    LIMITS = {
        'daily_loss': -0.05,      # -5% journalier
        'drawdown': -0.15,        # -15% drawdown max
        'volatility_spike': 3.0,   # 3x volatilité moyenne
        'consecutive_losses': 5,   # 5 trades perdants d'affilée
    }
    
    def check_daily_loss(self, pnl_today):
        if pnl_today < self.LIMITS['daily_loss']:
            return Action.HALT_TRADING
        return Action.CONTINUE
    
    def check_drawdown(self, current_drawdown):
        if current_drawdown < self.LIMITS['drawdown']:
            return Action.CLOSE_ALL_POSITIONS
        return Action.CONTINUE
    
    def check_volatility(self, current_vol, avg_vol):
        if current_vol > self.LIMITS['volatility_spike'] * avg_vol:
            return Action.REDUCE_SIZE
        return Action.CONTINUE
```

### Configuration

```yaml
risk_manager:
  position_sizing:
    method: "kelly_half"  # kelly_full, kelly_half, fixed_fraction
    max_position_per_trade: 0.10  # 10%
    max_positions_total: 10
  
  var:
    confidence_level: 0.95
    lookback_days: 252
    max_var_daily: 0.02  # 2% VaR max
  
  circuit_breakers:
    daily_loss_limit: -0.05
    max_drawdown: -0.15
    volatility_spike_factor: 3.0
    consecutive_losses: 5
  
  emergency:
    hard_stop_drawdown: -0.20
    auto_flatten: true
    notify_admin: true
```

### Alertes

| Niveau | Condition | Action |
|--------|-----------|--------|
| 🟡 Warning | VaR > 2% daily | Réduire positions 50% |
| 🟠 Critical | Drawdown > 10% | Stop nouvelles positions |
| 🔴 Emergency | Drawdown > 15% | Fermer tout |
| ⚫ Hard Stop | Drawdown > 20% | Flatten + Notify + Pause 24h |

---

**Date:** 2026-02-04  
**Décideur:** Kimi  
**Status:** APPROVED - Prêt pour implémentation