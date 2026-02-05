#!/usr/bin/env python3
"""
Monitoring Daemon for AUTOBOT Paper Trading Phase 4.

Provides 24/7 monitoring with:
- Real-time metrics tracking
- Alerts for anomalies (drawdown >15%, crash detection)
- Daily report generation
- Cron-compatible execution (every 10 minutes)

Usage:
    # Run once (for cron)
    python scripts/monitoring_daemon.py --once
    
    # Run as daemon
    python scripts/monitoring_daemon.py --daemon
    
    # Check status
    python scripts/monitoring_daemon.py --status
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/monitoring_daemon.log')
    ]
)
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class Alert:
    """Monitoring alert."""
    alert_id: str
    severity: AlertSeverity
    alert_type: str
    message: str
    value: float
    threshold: float
    timestamp: str
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "alert_type": self.alert_type,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
        }


@dataclass
class MonitoringSnapshot:
    """Point-in-time monitoring snapshot."""
    timestamp: str
    session_id: str
    is_running: bool
    current_capital: float
    initial_capital: float
    total_pnl: float
    roi_percent: float
    drawdown_percent: float
    trades_today: int
    total_trades: int
    win_rate: float
    alerts: List[Dict]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MonitoringDaemon:
    """
    24/7 Monitoring daemon for paper trading.
    
    Features:
    - Reads latest trading logs
    - Calculates real-time metrics
    - Generates alerts for anomalies
    - Saves monitoring snapshots
    """
    
    DRAWDOWN_WARNING_THRESHOLD = 15.0
    DRAWDOWN_CRITICAL_THRESHOLD = 20.0
    CONSECUTIVE_LOSS_THRESHOLD = 5
    ERROR_RATE_THRESHOLD = 5.0
    
    def __init__(
        self,
        log_dir: str = "logs",
        config_path: str = "config/binance_testnet.yml",
        initial_capital: float = 500.0
    ):
        """
        Initialize monitoring daemon.
        
        Args:
            log_dir: Directory containing trading logs
            config_path: Path to configuration file
            initial_capital: Initial capital amount
        """
        self.log_dir = Path(log_dir)
        self.config_path = Path(config_path)
        self.initial_capital = initial_capital
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._alerts: List[Alert] = []
        self._alert_count = 0
        self._last_snapshot: Optional[MonitoringSnapshot] = None
        
        logger.info(f"MonitoringDaemon initialized: log_dir={log_dir}")
    
    def _load_latest_trading_log(self) -> Optional[Dict[str, Any]]:
        """Load the most recent trading log file."""
        log_files = sorted(
            self.log_dir.glob("papier_trading_*.json"),
            reverse=True
        )
        
        if not log_files:
            logger.warning("No trading log files found")
            return None
        
        latest_file = log_files[0]
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded trading log: {latest_file}")
            return data
        except Exception as e:
            logger.error(f"Failed to load trading log: {e}")
            return None
    
    def _load_all_trading_logs(self, days: int = 7) -> List[Dict[str, Any]]:
        """Load trading logs for the specified number of days."""
        logs = []
        cutoff_date = date.today() - timedelta(days=days)
        
        for log_file in sorted(self.log_dir.glob("papier_trading_*.json")):
            try:
                date_str = log_file.stem.replace("papier_trading_", "")
                log_date = datetime.strptime(date_str, "%Y%m%d").date()
                
                if log_date >= cutoff_date:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        logs.append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load {log_file}: {e}")
        
        return logs
    
    def _check_process_running(self) -> bool:
        """Check if paper trading process is running."""
        pid_file = self.log_dir / "paper_trading.pid"
        
        if not pid_file.exists():
            return False
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            return False
    
    def _create_alert(
        self,
        severity: AlertSeverity,
        alert_type: str,
        message: str,
        value: float,
        threshold: float
    ) -> Alert:
        """Create and store an alert."""
        import uuid
        
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            severity=severity,
            alert_type=alert_type,
            message=message,
            value=value,
            threshold=threshold,
            timestamp=datetime.utcnow().isoformat(),
        )
        
        self._alerts.append(alert)
        self._alert_count += 1
        
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.ERROR,
            AlertSeverity.EMERGENCY: logging.CRITICAL,
        }.get(severity, logging.WARNING)
        
        logger.log(log_level, f"ALERT [{severity.value.upper()}]: {message}")
        
        return alert
    
    def _check_alerts(self, data: Dict[str, Any]) -> List[Alert]:
        """Check for alert conditions and create alerts."""
        new_alerts = []
        
        cumulative = data.get("cumulative_metrics", {})
        validation = data.get("validation_status", {})
        
        drawdown = cumulative.get("max_drawdown", 0.0)
        
        if drawdown >= self.DRAWDOWN_CRITICAL_THRESHOLD:
            alert = self._create_alert(
                severity=AlertSeverity.CRITICAL,
                alert_type="drawdown_critical",
                message=f"CRITICAL: Drawdown at {drawdown:.2f}% (threshold: {self.DRAWDOWN_CRITICAL_THRESHOLD}%)",
                value=drawdown,
                threshold=self.DRAWDOWN_CRITICAL_THRESHOLD,
            )
            new_alerts.append(alert)
        elif drawdown >= self.DRAWDOWN_WARNING_THRESHOLD:
            alert = self._create_alert(
                severity=AlertSeverity.WARNING,
                alert_type="drawdown_warning",
                message=f"WARNING: Drawdown at {drawdown:.2f}% (threshold: {self.DRAWDOWN_WARNING_THRESHOLD}%)",
                value=drawdown,
                threshold=self.DRAWDOWN_WARNING_THRESHOLD,
            )
            new_alerts.append(alert)
        
        consecutive_losses = cumulative.get("max_consecutive_losses", 0)
        if consecutive_losses >= self.CONSECUTIVE_LOSS_THRESHOLD:
            alert = self._create_alert(
                severity=AlertSeverity.WARNING,
                alert_type="consecutive_losses",
                message=f"WARNING: {consecutive_losses} consecutive losses",
                value=consecutive_losses,
                threshold=self.CONSECUTIVE_LOSS_THRESHOLD,
            )
            new_alerts.append(alert)
        
        error_count = cumulative.get("error_count", 0)
        total_trades = cumulative.get("total_trades", 1)
        error_rate = (error_count / max(1, total_trades)) * 100
        
        if error_rate >= self.ERROR_RATE_THRESHOLD:
            alert = self._create_alert(
                severity=AlertSeverity.WARNING,
                alert_type="high_error_rate",
                message=f"WARNING: Error rate at {error_rate:.2f}%",
                value=error_rate,
                threshold=self.ERROR_RATE_THRESHOLD,
            )
            new_alerts.append(alert)
        
        if not self._check_process_running():
            alert = self._create_alert(
                severity=AlertSeverity.CRITICAL,
                alert_type="process_not_running",
                message="CRITICAL: Paper trading process is not running",
                value=0,
                threshold=1,
            )
            new_alerts.append(alert)
        
        return new_alerts
    
    def run_check(self) -> MonitoringSnapshot:
        """
        Run a single monitoring check.
        
        Returns:
            MonitoringSnapshot with current status
        """
        data = self._load_latest_trading_log()
        
        if data is None:
            snapshot = MonitoringSnapshot(
                timestamp=datetime.utcnow().isoformat(),
                session_id="unknown",
                is_running=self._check_process_running(),
                current_capital=self.initial_capital,
                initial_capital=self.initial_capital,
                total_pnl=0.0,
                roi_percent=0.0,
                drawdown_percent=0.0,
                trades_today=0,
                total_trades=0,
                win_rate=0.0,
                alerts=[],
            )
            self._last_snapshot = snapshot
            return snapshot
        
        cumulative = data.get("cumulative_metrics", {})
        daily = data.get("daily_metrics", {})
        
        new_alerts = self._check_alerts(data)
        
        snapshot = MonitoringSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            session_id=data.get("session_id", "unknown"),
            is_running=self._check_process_running(),
            current_capital=cumulative.get("current_capital", self.initial_capital),
            initial_capital=cumulative.get("initial_capital", self.initial_capital),
            total_pnl=cumulative.get("net_pnl", 0.0),
            roi_percent=cumulative.get("roi_percent", 0.0),
            drawdown_percent=cumulative.get("max_drawdown", 0.0),
            trades_today=daily.get("trades_count", 0) if daily else 0,
            total_trades=cumulative.get("total_trades", 0),
            win_rate=cumulative.get("overall_win_rate", 0.0),
            alerts=[a.to_dict() for a in new_alerts],
        )
        
        self._save_snapshot(snapshot)
        self._last_snapshot = snapshot
        
        return snapshot
    
    def _save_snapshot(self, snapshot: MonitoringSnapshot) -> None:
        """Save monitoring snapshot to file."""
        snapshot_file = self.log_dir / f"monitoring_{date.today().strftime('%Y%m%d')}.json"
        
        snapshots = []
        if snapshot_file.exists():
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)
            except Exception:
                snapshots = []
        
        snapshots.append(snapshot.to_dict())
        
        if len(snapshots) > 1000:
            snapshots = snapshots[-1000:]
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status."""
        snapshot = self.run_check()
        
        return {
            "status": "running" if snapshot.is_running else "stopped",
            "last_check": snapshot.timestamp,
            "session_id": snapshot.session_id,
            "capital": {
                "initial": snapshot.initial_capital,
                "current": snapshot.current_capital,
                "pnl": snapshot.total_pnl,
                "roi_percent": snapshot.roi_percent,
            },
            "performance": {
                "total_trades": snapshot.total_trades,
                "trades_today": snapshot.trades_today,
                "win_rate": snapshot.win_rate,
                "drawdown_percent": snapshot.drawdown_percent,
            },
            "alerts": {
                "active_count": len([a for a in self._alerts if not a.acknowledged]),
                "total_count": len(self._alerts),
                "recent": [a.to_dict() for a in self._alerts[-5:]],
            },
        }
    
    async def run_daemon(self, interval_seconds: int = 600) -> None:
        """
        Run as a daemon with periodic checks.
        
        Args:
            interval_seconds: Seconds between checks (default: 10 minutes)
        """
        logger.info(f"Starting monitoring daemon (interval: {interval_seconds}s)")
        
        pid_file = self.log_dir / "monitoring_daemon.pid"
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        try:
            while True:
                try:
                    snapshot = self.run_check()
                    
                    logger.info(
                        f"Check complete: capital={snapshot.current_capital:.2f}, "
                        f"pnl={snapshot.total_pnl:.2f}, trades={snapshot.total_trades}, "
                        f"drawdown={snapshot.drawdown_percent:.2f}%"
                    )
                    
                    if snapshot.alerts:
                        for alert in snapshot.alerts:
                            logger.warning(f"Alert: {alert['message']}")
                    
                except Exception as e:
                    logger.error(f"Check failed: {e}")
                
                await asyncio.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user")
        finally:
            if pid_file.exists():
                pid_file.unlink()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AUTOBOT Paper Trading Monitoring Daemon"
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run a single check and exit'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as a daemon with periodic checks'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Print current status and exit'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=600,
        help='Check interval in seconds (default: 600 = 10 minutes)'
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default='logs',
        help='Directory containing trading logs'
    )
    
    args = parser.parse_args()
    
    daemon = MonitoringDaemon(log_dir=args.log_dir)
    
    if args.status:
        status = daemon.get_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.once:
        snapshot = daemon.run_check()
        print(json.dumps(snapshot.to_dict(), indent=2))
        return
    
    if args.daemon:
        asyncio.run(daemon.run_daemon(interval_seconds=args.interval))
        return
    
    snapshot = daemon.run_check()
    print(json.dumps(snapshot.to_dict(), indent=2))


if __name__ == "__main__":
    main()
