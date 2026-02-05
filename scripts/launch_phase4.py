#!/usr/bin/env python3
"""
Phase 4 Paper Trading Launcher for AUTOBOT.

Main entry point for launching the complete paper trading system:
- Grid Engine with 500 USDT fictif
- 24/7 Monitoring daemon
- Daily report generation
- Cron job setup for Kimi coordination

Usage:
    # Launch full system
    python scripts/launch_phase4.py
    
    # Launch with custom duration
    python scripts/launch_phase4.py --days 7
    
    # Resume previous session
    python scripts/launch_phase4.py --resume
    
    # Setup cron jobs only
    python scripts/launch_phase4.py --setup-cron
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/phase4_launcher.log')
    ]
)
logger = logging.getLogger(__name__)


class Phase4Launcher:
    """
    Orchestrates the complete Phase 4 paper trading system.
    
    Components:
    - PaperTradingRunner: Main grid trading engine
    - MonitoringDaemon: 24/7 monitoring with alerts
    - DailyReportGenerator: Automatic daily reports
    """
    
    def __init__(
        self,
        config_path: str = "config/binance_testnet.yml",
        duration_days: int = 7,
        resume: bool = False
    ):
        """
        Initialize Phase 4 launcher.
        
        Args:
            config_path: Path to configuration file
            duration_days: Number of days to run
            resume: Whether to resume previous session
        """
        self.config_path = Path(config_path)
        self.duration_days = duration_days
        self.resume = resume
        
        self.log_dir = Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._running = False
        self._shutdown_requested = False
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"Phase4Launcher initialized: config={config_path}, days={duration_days}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
    
    def _save_pid(self) -> None:
        """Save process ID for monitoring."""
        pid_file = self.log_dir / "paper_trading.pid"
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"PID saved: {os.getpid()}")
    
    def _remove_pid(self) -> None:
        """Remove PID file on shutdown."""
        pid_file = self.log_dir / "paper_trading.pid"
        if pid_file.exists():
            pid_file.unlink()
    
    def _save_session_info(self) -> None:
        """Save session information for monitoring and reports."""
        session_info = {
            "session_id": "papier_trading_phase4",
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "end_time": self._end_time.isoformat() if self._end_time else None,
            "duration_days": self.duration_days,
            "config_path": str(self.config_path),
            "initial_capital": 500.0,
            "symbol": "BTC/USDT",
            "grid_levels": 15,
            "range_percent": 14.0,
            "status": "running" if self._running else "stopped",
        }
        
        session_file = self.log_dir / "session_info.json"
        with open(session_file, 'w') as f:
            json.dump(session_info, f, indent=2)
    
    async def run(self) -> dict:
        """
        Run the complete Phase 4 paper trading system.
        
        Returns:
            Final report dictionary
        """
        self._running = True
        self._start_time = datetime.utcnow()
        self._end_time = self._start_time + timedelta(days=self.duration_days)
        
        self._save_pid()
        self._save_session_info()
        
        self._print_banner()
        
        try:
            from run_paper_trading import PaperTradingRunner
            
            runner = PaperTradingRunner(
                config_path=str(self.config_path),
                duration_days=self.duration_days,
                resume=self.resume
            )
            
            final_report = await runner.run()
            
            return final_report
            
        except ImportError as e:
            logger.error(f"Failed to import PaperTradingRunner: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error running paper trading: {e}")
            return {"error": str(e)}
        finally:
            self._running = False
            self._remove_pid()
            self._save_session_info()
    
    def _print_banner(self) -> None:
        """Print startup banner."""
        banner = """
================================================================================
     _   _   _ _____ ___  ____   ___ _____   ____  _   _    _    ____  _____   _  _   
    / \\ | | | |_   _/ _ \\| __ ) / _ \\_   _| |  _ \\| | | |  / \\  / ___|| ____| | || |  
   / _ \\| | | | | || | | |  _ \\| | | || |   | |_) | |_| | / _ \\ \\___ \\|  _|   | || |_ 
  / ___ \\ |_| | | || |_| | |_) | |_| || |   |  __/|  _  |/ ___ \\ ___) | |___  |__   _|
 /_/   \\_\\___/  |_| \\___/|____/ \\___/ |_|   |_|   |_| |_/_/   \\_\\____/|_____|    |_|  
                                                                                      
                         PAPER TRADING - PHASE 4
================================================================================

Configuration:
  - Symbol: BTC/USDT
  - Capital: 500 USDT (fictif)
  - Grid: 15 niveaux, +/-7%
  - Duree: {days} jours
  - Mode: PAPIER (pas de capital reel)

Criteres de validation J7:
  - Win rate >= 50%
  - Drawdown <= 20%
  - Profit factor >= 1.2
  - Min 50 trades

Demarrage: {start}
Fin prevue: {end}

================================================================================
""".format(
            days=self.duration_days,
            start=self._start_time.strftime("%Y-%m-%d %H:%M:%S UTC") if self._start_time else "N/A",
            end=self._end_time.strftime("%Y-%m-%d %H:%M:%S UTC") if self._end_time else "N/A",
        )
        print(banner)
    
    @staticmethod
    def setup_cron_jobs() -> None:
        """
        Setup cron jobs for monitoring and reports.
        
        Creates:
        - Monitoring check every 10 minutes
        - Daily report at midnight
        """
        scripts_dir = Path(__file__).parent.absolute()
        python_path = sys.executable
        
        cron_entries = [
            f"*/10 * * * * {python_path} {scripts_dir}/monitoring_daemon.py --once >> /tmp/autobot_monitoring.log 2>&1",
            f"0 0 * * * {python_path} {scripts_dir}/daily_report_generator.py --markdown >> /tmp/autobot_daily_report.log 2>&1",
        ]
        
        print("\n" + "="*60)
        print("CRON JOBS POUR MONITORING AUTOBOT")
        print("="*60)
        print("\nAjoutez ces lignes a votre crontab (crontab -e):\n")
        
        for entry in cron_entries:
            print(entry)
        
        print("\n" + "="*60)
        print("\nPour coordination avec Kimi, utilisez:")
        print(f"  {python_path} {scripts_dir}/monitoring_daemon.py --status")
        print("="*60 + "\n")
    
    @staticmethod
    def get_status() -> dict:
        """Get current system status."""
        log_dir = Path("logs")
        
        session_file = log_dir / "session_info.json"
        if session_file.exists():
            with open(session_file, 'r') as f:
                session_info = json.load(f)
        else:
            session_info = {"status": "not_started"}
        
        pid_file = log_dir / "paper_trading.pid"
        is_running = False
        if pid_file.exists():
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                is_running = True
            except (ProcessLookupError, ValueError):
                is_running = False
        
        session_info["is_running"] = is_running
        
        return session_info


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AUTOBOT Phase 4 Paper Trading Launcher"
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config/binance_testnet.yml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to run (default: 7)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume previous session'
    )
    parser.add_argument(
        '--setup-cron',
        action='store_true',
        help='Setup cron jobs and exit'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Print current status and exit'
    )
    
    args = parser.parse_args()
    
    if args.setup_cron:
        Phase4Launcher.setup_cron_jobs()
        return
    
    if args.status:
        status = Phase4Launcher.get_status()
        print(json.dumps(status, indent=2))
        return
    
    launcher = Phase4Launcher(
        config_path=args.config,
        duration_days=args.days,
        resume=args.resume
    )
    
    try:
        final_report = asyncio.run(launcher.run())
        
        if final_report.get('error'):
            logger.error(f"Session ended with error: {final_report['error']}")
            sys.exit(1)
        
        print("\n" + "="*60)
        print("SESSION TERMINEE")
        print("="*60)
        print(json.dumps(final_report, indent=2, ensure_ascii=False))
        print("="*60 + "\n")
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("Session interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
