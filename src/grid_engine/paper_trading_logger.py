"""
Paper Trading Logger for AUTOBOT Grid Trading Engine.

Provides daily JSON logging for paper trading sessions with:
- Trade records
- Daily performance metrics
- Cumulative statistics
- Validation criteria tracking
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TradeType(Enum):
    """Type of trade."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradeRecord:
    """Record of a single trade."""
    trade_id: str
    timestamp: str
    symbol: str
    side: str
    price: float
    quantity: float
    value: float
    fee: float
    pnl: float = 0.0
    level_id: int = 0
    order_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyMetrics:
    """Daily performance metrics."""
    date: str
    trades_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    max_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_trade_pnl: float = 0.0
    volume_traded: float = 0.0
    start_balance: float = 0.0
    end_balance: float = 0.0
    roi_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CumulativeMetrics:
    """Cumulative metrics across all days."""
    total_days: int = 0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    overall_win_rate: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    initial_capital: float = 500.0
    current_capital: float = 500.0
    roi_percent: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_date: str = ""
    best_day_pnl: float = 0.0
    best_day_date: str = ""
    worst_day_pnl: float = 0.0
    worst_day_date: str = ""
    avg_daily_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    uptime_percent: float = 100.0
    error_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationStatus:
    """Validation criteria status for GO/NO-GO decision."""
    min_trades_met: bool = False
    min_win_rate_met: bool = False
    max_drawdown_met: bool = True
    min_profit_factor_met: bool = False
    min_sharpe_met: bool = False
    max_consecutive_losses_met: bool = True
    min_uptime_met: bool = True
    max_error_rate_met: bool = True
    overall_status: str = "PENDING"
    recommendation: str = "En cours de validation..."
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperTradingLogger:
    """
    Logger for paper trading sessions.
    
    Creates daily JSON log files with format: papier_trading_YYYYMMDD.json
    Tracks trades, metrics, and validation criteria.
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        initial_capital: float = 500.0,
        session_id: str = "papier_trading_phase3"
    ):
        """
        Initialize paper trading logger.
        
        Args:
            log_dir: Directory for log files
            initial_capital: Initial capital in EUR
            session_id: Unique session identifier
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_id = session_id
        self.initial_capital = initial_capital
        
        self._current_date: Optional[date] = None
        self._daily_trades: List[TradeRecord] = []
        self._daily_metrics: Optional[DailyMetrics] = None
        self._cumulative: CumulativeMetrics = CumulativeMetrics(
            initial_capital=initial_capital,
            current_capital=initial_capital
        )
        self._validation: ValidationStatus = ValidationStatus()
        self._daily_pnls: List[float] = []
        
        self._start_time = datetime.utcnow()
        self._last_error_time: Optional[datetime] = None
        
        logger.info(f"PaperTradingLogger initialized: session={session_id}, capital={initial_capital}")
    
    def _get_log_filename(self, log_date: date) -> Path:
        """Get log filename for a specific date."""
        return self.log_dir / f"papier_trading_{log_date.strftime('%Y%m%d')}.json"
    
    def _ensure_daily_initialized(self) -> None:
        """Ensure daily tracking is initialized for current date."""
        today = date.today()
        
        if self._current_date != today:
            if self._current_date is not None:
                self._save_daily_log()
            
            self._current_date = today
            self._daily_trades = []
            self._daily_metrics = DailyMetrics(
                date=today.isoformat(),
                start_balance=self._cumulative.current_capital
            )
            
            logger.info(f"New trading day initialized: {today}")
    
    def record_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        fee: float = 0.0,
        pnl: float = 0.0,
        level_id: int = 0,
        order_id: str = ""
    ) -> TradeRecord:
        """
        Record a trade.
        
        Args:
            trade_id: Unique trade identifier
            symbol: Trading pair
            side: "buy" or "sell"
            price: Execution price
            quantity: Trade quantity
            fee: Trading fee
            pnl: Profit/loss (for sell trades)
            level_id: Grid level ID
            order_id: Associated order ID
            
        Returns:
            Created TradeRecord
        """
        self._ensure_daily_initialized()
        
        value = price * quantity
        
        trade = TradeRecord(
            trade_id=trade_id,
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            value=value,
            fee=fee,
            pnl=pnl,
            level_id=level_id,
            order_id=order_id
        )
        
        self._daily_trades.append(trade)
        self._update_metrics(trade)
        
        logger.info(f"Trade recorded: {side} {quantity} {symbol} @ {price}, PnL={pnl:.2f}")
        
        return trade
    
    def _update_metrics(self, trade: TradeRecord) -> None:
        """Update metrics after a trade."""
        if self._daily_metrics is None:
            return
        
        self._daily_metrics.trades_count += 1
        self._daily_metrics.total_fees += trade.fee
        self._daily_metrics.volume_traded += trade.value
        
        if trade.side.lower() == "buy":
            self._daily_metrics.buy_count += 1
        else:
            self._daily_metrics.sell_count += 1
            self._daily_metrics.total_pnl += trade.pnl
            
            if trade.pnl > 0:
                self._daily_metrics.win_count += 1
                self._cumulative.consecutive_wins += 1
                self._cumulative.consecutive_losses = 0
                self._cumulative.max_consecutive_wins = max(
                    self._cumulative.max_consecutive_wins,
                    self._cumulative.consecutive_wins
                )
            elif trade.pnl < 0:
                self._daily_metrics.loss_count += 1
                self._cumulative.consecutive_losses += 1
                self._cumulative.consecutive_wins = 0
                self._cumulative.max_consecutive_losses = max(
                    self._cumulative.max_consecutive_losses,
                    self._cumulative.consecutive_losses
                )
            
            if trade.pnl > self._daily_metrics.best_trade:
                self._daily_metrics.best_trade = trade.pnl
            if trade.pnl < self._daily_metrics.worst_trade:
                self._daily_metrics.worst_trade = trade.pnl
        
        self._cumulative.total_trades += 1
        self._cumulative.total_fees += trade.fee
        
        if trade.side.lower() == "sell":
            self._cumulative.total_pnl += trade.pnl
            self._cumulative.current_capital += trade.pnl - trade.fee
            
            if trade.pnl > 0:
                self._cumulative.total_wins += 1
            elif trade.pnl < 0:
                self._cumulative.total_losses += 1
        
        self._calculate_derived_metrics()
        self._update_validation_status()
    
    def _calculate_derived_metrics(self) -> None:
        """Calculate derived metrics."""
        if self._daily_metrics is None:
            return
        
        sell_count = self._daily_metrics.sell_count
        if sell_count > 0:
            self._daily_metrics.win_rate = (
                self._daily_metrics.win_count / sell_count * 100
            )
            self._daily_metrics.avg_trade_pnl = (
                self._daily_metrics.total_pnl / sell_count
            )
        
        self._daily_metrics.net_pnl = (
            self._daily_metrics.total_pnl - self._daily_metrics.total_fees
        )
        self._daily_metrics.end_balance = (
            self._daily_metrics.start_balance + self._daily_metrics.net_pnl
        )
        
        if self._daily_metrics.start_balance > 0:
            self._daily_metrics.roi_percent = (
                self._daily_metrics.net_pnl / self._daily_metrics.start_balance * 100
            )
        
        total_sells = self._cumulative.total_wins + self._cumulative.total_losses
        if total_sells > 0:
            self._cumulative.overall_win_rate = (
                self._cumulative.total_wins / total_sells * 100
            )
        
        self._cumulative.net_pnl = (
            self._cumulative.total_pnl - self._cumulative.total_fees
        )
        
        if self._cumulative.initial_capital > 0:
            self._cumulative.roi_percent = (
                (self._cumulative.current_capital - self._cumulative.initial_capital)
                / self._cumulative.initial_capital * 100
            )
        
        drawdown = (
            (self._cumulative.initial_capital - self._cumulative.current_capital)
            / self._cumulative.initial_capital * 100
        )
        if drawdown > self._cumulative.max_drawdown:
            self._cumulative.max_drawdown = drawdown
            self._cumulative.max_drawdown_date = date.today().isoformat()
        
        if self._daily_metrics.net_pnl > self._cumulative.best_day_pnl:
            self._cumulative.best_day_pnl = self._daily_metrics.net_pnl
            self._cumulative.best_day_date = date.today().isoformat()
        if self._daily_metrics.net_pnl < self._cumulative.worst_day_pnl:
            self._cumulative.worst_day_pnl = self._daily_metrics.net_pnl
            self._cumulative.worst_day_date = date.today().isoformat()
        
        self._calculate_sharpe_ratio()
        self._calculate_profit_factor()
    
    def _calculate_sharpe_ratio(self) -> None:
        """Calculate Sharpe ratio from daily PnLs."""
        if len(self._daily_pnls) < 2:
            return
        
        import statistics
        
        avg_return = statistics.mean(self._daily_pnls)
        std_return = statistics.stdev(self._daily_pnls)
        
        if std_return > 0:
            self._cumulative.sharpe_ratio = (avg_return / std_return) * (252 ** 0.5)
    
    def _calculate_profit_factor(self) -> None:
        """Calculate profit factor."""
        gross_profit = sum(t.pnl for t in self._daily_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self._daily_trades if t.pnl < 0))
        
        if gross_loss > 0:
            self._cumulative.profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            self._cumulative.profit_factor = float('inf')
    
    def _update_validation_status(self) -> None:
        """Update validation criteria status."""
        self._validation.min_trades_met = self._cumulative.total_trades >= 50
        self._validation.min_win_rate_met = self._cumulative.overall_win_rate >= 50.0
        self._validation.max_drawdown_met = self._cumulative.max_drawdown <= 20.0
        self._validation.min_profit_factor_met = self._cumulative.profit_factor >= 1.2
        self._validation.min_sharpe_met = self._cumulative.sharpe_ratio >= 0.5
        self._validation.max_consecutive_losses_met = (
            self._cumulative.max_consecutive_losses <= 10
        )
        self._validation.min_uptime_met = self._cumulative.uptime_percent >= 95.0
        self._validation.max_error_rate_met = (
            self._cumulative.error_count / max(1, self._cumulative.total_trades) * 100 <= 5.0
        )
        
        criteria_met = [
            self._validation.min_trades_met,
            self._validation.min_win_rate_met,
            self._validation.max_drawdown_met,
            self._validation.min_profit_factor_met,
            self._validation.min_sharpe_met,
            self._validation.max_consecutive_losses_met,
            self._validation.min_uptime_met,
            self._validation.max_error_rate_met,
        ]
        
        met_count = sum(criteria_met)
        total_count = len(criteria_met)
        
        if met_count == total_count:
            self._validation.overall_status = "GO"
            self._validation.recommendation = (
                "Tous les criteres sont valides. Pret pour le trading reel avec 500EUR."
            )
        elif met_count >= total_count - 2:
            self._validation.overall_status = "REVIEW"
            self._validation.recommendation = (
                f"{met_count}/{total_count} criteres valides. Revision recommandee."
            )
        else:
            self._validation.overall_status = "NO-GO"
            self._validation.recommendation = (
                f"Seulement {met_count}/{total_count} criteres valides. "
                "Continuer le papier trading."
            )
    
    def record_error(self, error_message: str) -> None:
        """Record an error event."""
        self._cumulative.error_count += 1
        self._last_error_time = datetime.utcnow()
        logger.error(f"Paper trading error: {error_message}")
    
    def _save_daily_log(self) -> None:
        """Save daily log to JSON file."""
        if self._current_date is None or self._daily_metrics is None:
            return
        
        self._daily_pnls.append(self._daily_metrics.net_pnl)
        
        if self._cumulative.total_days > 0:
            self._cumulative.avg_daily_pnl = (
                self._cumulative.net_pnl / self._cumulative.total_days
            )
        
        self._cumulative.total_days += 1
        
        log_data = {
            "session_id": self.session_id,
            "date": self._current_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "trades": [t.to_dict() for t in self._daily_trades],
            "daily_metrics": self._daily_metrics.to_dict(),
            "cumulative_metrics": self._cumulative.to_dict(),
            "validation_status": self._validation.to_dict(),
        }
        
        log_file = self._get_log_filename(self._current_date)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Daily log saved: {log_file}")
    
    def save_current_state(self) -> None:
        """Save current state to log file."""
        self._ensure_daily_initialized()
        self._save_daily_log()
    
    def get_daily_report(self) -> Dict[str, Any]:
        """Get current daily report."""
        self._ensure_daily_initialized()
        
        return {
            "session_id": self.session_id,
            "date": self._current_date.isoformat() if self._current_date else None,
            "trades_count": len(self._daily_trades),
            "daily_metrics": self._daily_metrics.to_dict() if self._daily_metrics else None,
            "cumulative_metrics": self._cumulative.to_dict(),
            "validation_status": self._validation.to_dict(),
        }
    
    def get_final_report(self) -> Dict[str, Any]:
        """Get final report for the session."""
        self.save_current_state()
        
        return {
            "session_id": self.session_id,
            "session_start": self._start_time.isoformat(),
            "session_end": datetime.utcnow().isoformat(),
            "duration_days": self._cumulative.total_days,
            "initial_capital": self.initial_capital,
            "final_capital": self._cumulative.current_capital,
            "total_pnl": self._cumulative.net_pnl,
            "roi_percent": self._cumulative.roi_percent,
            "total_trades": self._cumulative.total_trades,
            "win_rate": self._cumulative.overall_win_rate,
            "max_drawdown": self._cumulative.max_drawdown,
            "sharpe_ratio": self._cumulative.sharpe_ratio,
            "profit_factor": self._cumulative.profit_factor,
            "validation_status": self._validation.to_dict(),
            "recommendation": self._validation.recommendation,
        }
    
    def load_previous_state(self) -> bool:
        """Load previous state from most recent log file."""
        log_files = sorted(self.log_dir.glob("papier_trading_*.json"), reverse=True)
        
        if not log_files:
            logger.info("No previous state found")
            return False
        
        try:
            with open(log_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "cumulative_metrics" in data:
                cum = data["cumulative_metrics"]
                self._cumulative = CumulativeMetrics(**cum)
            
            if "validation_status" in data:
                val = data["validation_status"]
                self._validation = ValidationStatus(**val)
            
            logger.info(f"Loaded previous state from {log_files[0]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load previous state: {e}")
            return False
