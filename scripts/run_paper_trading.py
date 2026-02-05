#!/usr/bin/env python3
"""
Paper Trading Runner for AUTOBOT Grid Trading Engine.

Phase 3: Validation strategie Grid sans risque avant capital reel
- Capital fictif: 500 EUR
- Duree: 7 jours minimum
- Mode: PAPIER uniquement (pas 1 EUR reel)

Usage:
    python scripts/run_paper_trading.py --config config/binance_testnet.yml
    
    # With custom duration
    python scripts/run_paper_trading.py --days 7
    
    # Resume previous session
    python scripts/run_paper_trading.py --resume
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/paper_trading_runner.log')
    ]
)
logger = logging.getLogger(__name__)


class PaperTradingRunner:
    """
    Main runner for paper trading sessions.
    
    Manages the Grid Engine in paper trading mode with:
    - 24/7 monitoring
    - Daily performance logging
    - Automatic restart on failure
    - Graceful shutdown
    """
    
    def __init__(
        self,
        config_path: str = "config/binance_testnet.yml",
        duration_days: int = 7,
        resume: bool = False
    ):
        """
        Initialize paper trading runner.
        
        Args:
            config_path: Path to configuration file
            duration_days: Number of days to run
            resume: Whether to resume previous session
        """
        self.config_path = Path(config_path)
        self.duration_days = duration_days
        self.resume = resume
        
        self.config = self._load_config()
        self._running = False
        self._shutdown_requested = False
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        
        self._grid_calculator = None
        self._order_manager = None
        self._binance_connector = None
        self._position_tracker = None
        self._risk_manager = None
        self._logger = None
        
        self._current_price: float = 0.0
        self._price_history: list = []
        self._last_metrics_time: Optional[datetime] = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"PaperTradingRunner initialized: config={config_path}, days={duration_days}")
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        logger.info(f"Configuration loaded from {self.config_path}")
        return config
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
    
    async def initialize(self) -> bool:
        """
        Initialize all components.
        
        Returns:
            True if initialization successful
        """
        try:
            from grid_engine.grid_calculator import GridCalculator, GridConfig
            from grid_engine.order_manager import GridOrderManager
            from grid_engine.binance_connector import BinanceConnector, BinanceConfig
            from grid_engine.position_tracker import PositionTracker
            from grid_engine.risk_manager import GridRiskManager
            from grid_engine.paper_trading_logger import PaperTradingLogger
            
            grid_config = self.config.get('grid', {})
            self._grid_calculator = GridCalculator(GridConfig(
                symbol=grid_config.get('symbol', 'BTC/USDT'),
                total_capital=grid_config.get('total_capital', 500.0),
                num_levels=grid_config.get('num_levels', 15),
                range_percent=grid_config.get('range_percent', 14.0),
                profit_per_level=grid_config.get('profit_per_level', 0.8),
                fee_percent=0.1,
            ))
            
            binance_config = BinanceConfig(
                api_key=os.getenv('BINANCE_TESTNET_API_KEY', ''),
                api_secret=os.getenv('BINANCE_TESTNET_API_SECRET', ''),
                testnet=True,
            )
            self._binance_connector = BinanceConnector(
                config=binance_config,
                paper_trading=True
            )
            
            paper_config = self.config.get('paper_trading', {})
            initial_balance = paper_config.get('initial_usdt_balance', 540.0)
            self._binance_connector._paper_balance['USDT'] = initial_balance
            
            self._order_manager = GridOrderManager(
                grid_calculator=self._grid_calculator,
                exchange_client=self._binance_connector,
                paper_trading=True
            )
            
            self._position_tracker = PositionTracker(
                symbol=grid_config.get('symbol', 'BTC/USDT'),
                initial_capital=grid_config.get('total_capital', 500.0)
            )
            
            risk_config = self.config.get('risk', {})
            self._risk_manager = GridRiskManager(
                initial_capital=grid_config.get('total_capital', 500.0),
                max_drawdown_percent=risk_config.get('max_drawdown_percent', 25.0),
                daily_loss_limit=risk_config.get('daily_loss_limit', 50.0),
                global_stop_percent=risk_config.get('global_stop_percent', 20.0),
            )
            
            session_config = self.config.get('session', {})
            self._logger = PaperTradingLogger(
                log_dir='logs',
                initial_capital=grid_config.get('total_capital', 500.0),
                session_id=session_config.get('session_id', 'papier_trading_phase3')
            )
            
            if self.resume:
                self._logger.load_previous_state()
            
            await self._binance_connector.connect()
            
            logger.info("All components initialized successfully")
            return True
            
        except ImportError as e:
            logger.error(f"Failed to import required modules: {e}")
            return False
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    async def run(self) -> dict:
        """
        Run the paper trading session.
        
        Returns:
            Final report dictionary
        """
        if not await self.initialize():
            return {"error": "Initialization failed"}
        
        self._running = True
        self._start_time = datetime.utcnow()
        self._end_time = self._start_time + timedelta(days=self.duration_days)
        
        logger.info(f"Paper trading started: {self._start_time}")
        logger.info(f"Scheduled end: {self._end_time}")
        logger.info(f"Initial capital: {self.config.get('grid', {}).get('total_capital', 500)} EUR")
        
        try:
            initial_price = await self._get_current_price()
            if initial_price > 0:
                self._grid_calculator.calculate_grid(initial_price)
                await self._order_manager.initialize_grid_orders()
                logger.info(f"Grid initialized at price {initial_price}")
            
            self._order_manager.on_order_filled(self._on_order_filled)
            
            while self._running and not self._shutdown_requested:
                if datetime.utcnow() >= self._end_time:
                    logger.info("Session duration completed")
                    break
                
                await self._trading_loop()
                
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
            self._logger.record_error(str(e))
        
        finally:
            await self._shutdown()
        
        return self._logger.get_final_report()
    
    async def _trading_loop(self) -> None:
        """Main trading loop iteration."""
        try:
            price = await self._get_current_price()
            if price <= 0:
                return
            
            self._current_price = price
            self._price_history.append({
                'timestamp': datetime.utcnow().isoformat(),
                'price': price
            })
            
            if len(self._price_history) > 3600:
                self._price_history = self._price_history[-3600:]
            
            await self._binance_connector.simulate_price_update(
                self._grid_calculator.config.symbol,
                price
            )
            
            filled_orders = await self._order_manager.check_fills_at_price(price)
            for order in filled_orders:
                logger.info(f"Order filled at price {price}: {order.side.value} {order.quantity}")
            
            can_trade, reason, risk_data = self._risk_manager.check_risk()
            if not can_trade:
                logger.warning(f"Trading halted: {reason}")
            
            await self._log_metrics_if_needed()
            
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
            self._logger.record_error(str(e))
    
    async def _get_current_price(self) -> float:
        """Get current price from exchange or simulation."""
        try:
            ticker = await self._binance_connector.get_ticker(
                self._grid_calculator.config.symbol
            )
            return ticker.get('last', 0.0)
        except Exception as e:
            logger.error(f"Failed to get price: {e}")
            return self._current_price or 50000.0
    
    async def _on_order_filled(self, order) -> None:
        """Handle order filled event."""
        try:
            from grid_engine.grid_calculator import GridSide
            
            pnl = 0.0
            if order.side == GridSide.SELL:
                pnl = self._order_manager.total_profit - getattr(self, '_last_profit', 0.0)
                self._last_profit = self._order_manager.total_profit
            
            self._logger.record_trade(
                trade_id=order.order_id,
                symbol=order.symbol,
                side=order.side.value,
                price=order.average_fill_price or order.price,
                quantity=order.filled_quantity,
                fee=order.fee,
                pnl=pnl,
                level_id=order.level_id,
                order_id=order.exchange_order_id or ""
            )
            
            self._position_tracker.record_trade(
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.filled_quantity,
                price=order.average_fill_price or order.price,
                fee=order.fee
            )
            
            if pnl != 0:
                self._risk_manager.record_pnl(pnl)
            
            logger.info(
                f"Trade logged: {order.side.value} {order.filled_quantity} @ "
                f"{order.average_fill_price or order.price}, PnL={pnl:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error handling order fill: {e}")
    
    async def _log_metrics_if_needed(self) -> None:
        """Log metrics at configured interval."""
        metrics_interval = self.config.get('monitoring', {}).get('metrics_interval_seconds', 60)
        
        now = datetime.utcnow()
        if self._last_metrics_time is None:
            self._last_metrics_time = now
            return
        
        if (now - self._last_metrics_time).total_seconds() >= metrics_interval:
            self._last_metrics_time = now
            
            report = self._logger.get_daily_report()
            
            logger.info(
                f"Metrics: trades={report.get('trades_count', 0)}, "
                f"PnL={report.get('cumulative_metrics', {}).get('net_pnl', 0):.2f}, "
                f"ROI={report.get('cumulative_metrics', {}).get('roi_percent', 0):.2f}%"
            )
    
    async def _shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Initiating shutdown...")
        
        self._running = False
        
        if self._order_manager:
            await self._order_manager.cancel_all_orders()
        
        if self._binance_connector:
            await self._binance_connector.disconnect()
        
        if self._logger:
            self._logger.save_current_state()
            
            final_report = self._logger.get_final_report()
            
            report_path = Path('logs') / f"final_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_path, 'w') as f:
                json.dump(final_report, f, indent=2)
            
            logger.info(f"Final report saved: {report_path}")
            
            print("\n" + "="*60)
            print("RAPPORT FINAL - PAPIER TRADING PHASE 3")
            print("="*60)
            print(f"Session: {final_report.get('session_id')}")
            print(f"Duree: {final_report.get('duration_days')} jours")
            print(f"Capital initial: {final_report.get('initial_capital'):.2f} EUR")
            print(f"Capital final: {final_report.get('final_capital'):.2f} EUR")
            print(f"P&L total: {final_report.get('total_pnl'):.2f} EUR")
            print(f"ROI: {final_report.get('roi_percent'):.2f}%")
            print(f"Trades: {final_report.get('total_trades')}")
            print(f"Win rate: {final_report.get('win_rate'):.1f}%")
            print(f"Max drawdown: {final_report.get('max_drawdown'):.2f}%")
            print(f"Sharpe ratio: {final_report.get('sharpe_ratio'):.2f}")
            print("-"*60)
            print(f"STATUT: {final_report.get('validation_status', {}).get('overall_status')}")
            print(f"RECOMMANDATION: {final_report.get('recommendation')}")
            print("="*60 + "\n")
        
        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AUTOBOT Paper Trading Runner - Phase 3"
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
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("AUTOBOT PAPIER TRADING - PHASE 3")
    print("="*60)
    print(f"Configuration: {args.config}")
    print(f"Duree: {args.days} jours")
    print(f"Mode: PAPIER (pas de capital reel)")
    print(f"Capital fictif: 500 EUR")
    print("="*60 + "\n")
    
    runner = PaperTradingRunner(
        config_path=args.config,
        duration_days=args.days,
        resume=args.resume
    )
    
    try:
        final_report = asyncio.run(runner.run())
        
        if final_report.get('error'):
            logger.error(f"Session ended with error: {final_report['error']}")
            sys.exit(1)
        
        validation_status = final_report.get('validation_status', {}).get('overall_status', 'UNKNOWN')
        if validation_status == 'GO':
            logger.info("Session completed successfully - READY FOR REAL TRADING")
            sys.exit(0)
        else:
            logger.info(f"Session completed - Status: {validation_status}")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("Session interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
