"""
Trading Instance - Instance individuelle de trading
"""

import logging
import uuid
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import time

from .websocket_client import TickerData

logger = logging.getLogger(__name__)


class InstanceStatus(Enum):
    """Statut d'une instance"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class Trade:
    """Trade exécuté"""
    id: str
    side: str  # 'buy', 'sell'
    price: float
    volume: float
    timestamp: datetime
    profit: Optional[float] = None


@dataclass
class Position:
    """Position ouverte"""
    id: str
    buy_price: float
    volume: float
    sell_price: Optional[float] = None
    status: str = "open"  # open, closed
    open_time: datetime = field(default_factory=datetime.now)
    close_time: Optional[datetime] = None
    profit: Optional[float] = None


class TradingInstance:
    """
    Instance de trading autonome gérée par l'Orchestrateur.
    
    Chaque instance a:
    - Son propre capital
    - Sa propre stratégie
    - Son historique de trades
    - Sa gestion des risques
    """
    
    def __init__(self, instance_id: str, config: Any, orchestrator: Any):
        self.id = instance_id
        self.config = config
        self.orchestrator = orchestrator
        
        # État
        self.status = InstanceStatus.INITIALIZING
        self._lock = threading.Lock()
        
        # Capital
        self._initial_capital = config.initial_capital
        self._current_capital = config.initial_capital
        self._allocated_capital = 0.0  # Capital alloué aux positions ouvertes
        
        # Positions et trades
        self._positions: Dict[str, Position] = {}
        self._trades: List[Trade] = []
        self._open_orders: Dict[str, Any] = {}
        
        # Performance
        self._win_count = 0
        self._loss_count = 0
        self._win_streak = 0
        self._max_drawdown = 0.0
        self._peak_capital = config.initial_capital
        
        # Prix
        self._last_price: Optional[float] = None
        self._price_history: List[tuple] = []  # [(timestamp, price), ...]
        self._max_history_size = 1000
        
        # Stratégie
        self._strategy = None  # Sera initialisé selon config.strategy
        
        # Callbacks
        self._on_trade: Optional[Callable] = None
        self._on_position_open: Optional[Callable] = None
        self._on_position_close: Optional[Callable] = None
        
        # Thread
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        logger.info(f"📊 Instance {self.id} initialisée: {config.name}")
    
    def start(self):
        """Démarre l'instance"""
        if self.status == InstanceStatus.RUNNING:
            return
        
        self.status = InstanceStatus.RUNNING
        self._stop_event.clear()
        
        # Initialisation stratégie
        self._init_strategy()
        
        logger.info(f"▶️ Instance {self.id} démarrée")
    
    def stop(self):
        """Arrête l'instance proprement"""
        logger.info(f"⏹️ Arrêt instance {self.id}...")
        self.status = InstanceStatus.STOPPING
        self._stop_event.set()
        
        # Annule ordres ouverts
        self._cancel_all_orders()
        
        # Attente positions fermées
        self._wait_positions_closed()
        
        self.status = InstanceStatus.STOPPED
        logger.info(f"✅ Instance {self.id} arrêtée")
    
    def pause(self):
        """Met en pause (pas de nouveaux trades)"""
        self.status = InstanceStatus.PAUSED
        logger.info(f"⏸️ Instance {self.id} en pause")
    
    def resume(self):
        """Reprend après pause"""
        self.status = InstanceStatus.RUNNING
        logger.info(f"▶️ Instance {self.id} reprise")
    
    def emergency_stop(self):
        """Arrêt d'urgence immédiat"""
        logger.warning(f"🚨 ARRÊT URGENCE instance {self.id}")
        self._stop_event.set()
        
        # Ferme tout immédiatement (market orders)
        self._close_all_positions_market()
        
        self.status = InstanceStatus.STOPPED
    
    def _init_strategy(self):
        """Initialise la stratégie selon configuration"""
        strategy_name = self.config.strategy
        
        if strategy_name == 'grid':
            from .strategies import GridStrategy
            self._strategy = GridStrategy(self)
        elif strategy_name == 'trend':
            from .strategies import TrendStrategy
            self._strategy = TrendStrategy(self)
        else:
            logger.warning(f"⚠️ Stratégie inconnue: {strategy_name}, fallback sur Grid")
            from .strategies import GridStrategy
            self._strategy = GridStrategy(self)
        
        logger.info(f"🎯 Stratégie {strategy_name} chargée pour {self.id}")
    
    def on_price_update(self, data: TickerData):
        """Appelé quand nouveau prix reçu via WebSocket"""
        with self._lock:
            self._last_price = data.price
            self._price_history.append((datetime.now(), data.price))
            
            # Limite historique
            if len(self._price_history) > self._max_history_size:
                self._price_history = self._price_history[-self._max_history_size:]
        
        # Notifie stratégie
        if self._strategy and self.status == InstanceStatus.RUNNING:
            self._strategy.on_price(data.price)
    
    def can_open_position(self, order_value: float) -> bool:
        """Vérifie si peut ouvrir position"""
        with self._lock:
            # Capital disponible
            available = self._current_capital - self._allocated_capital
            
            # Limites
            max_positions = 10
            
            return (
                self.status == InstanceStatus.RUNNING and
                available >= order_value and
                len(self._positions) < max_positions
            )
    
    def open_position(self, price: float, volume: float) -> Optional[Position]:
        """Ouvre une position"""
        order_value = price * volume
        
        if not self.can_open_position(order_value):
            return None
        
        with self._lock:
            position_id = str(uuid.uuid4())[:8]
            
            position = Position(
                id=position_id,
                buy_price=price,
                volume=volume
            )
            
            self._positions[position_id] = position
            self._allocated_capital += order_value
            
            logger.info(f"📈 Position ouverte {self.id}/{position_id}: {volume} @ {price:.2f}€")
            
            if self._on_position_open:
                self._on_position_open(self, position)
            
            return position
    
    def close_position(self, position_id: str, sell_price: float) -> Optional[float]:
        """Ferme une position et calcule profit"""
        with self._lock:
            if position_id not in self._positions:
                return None
            
            position = self._positions[position_id]
            
            if position.status != "open":
                return None
            
            # Calcule profit
            gross_profit = (sell_price - position.buy_price) * position.volume
            
            # Frais (0.42% total - maker + taker)
            fees = (position.buy_price + sell_price) * position.volume * 0.0042
            
            net_profit = gross_profit - fees
            
            # Met à jour position
            position.sell_price = sell_price
            position.status = "closed"
            position.close_time = datetime.now()
            position.profit = net_profit
            
            # Met à jour capital
            self._current_capital += net_profit
            self._allocated_capital -= position.buy_price * position.volume
            
            # Met à jour performance
            if net_profit > 0:
                self._win_count += 1
                self._win_streak += 1
            else:
                self._loss_count += 1
                self._win_streak = 0
            
            # Check drawdown
            if self._current_capital > self._peak_capital:
                self._peak_capital = self._current_capital
            else:
                drawdown = (self._peak_capital - self._current_capital) / self._peak_capital
                self._max_drawdown = max(self._max_drawdown, drawdown)
            
            logger.info(f"📉 Position fermée {self.id}/{position_id}: Profit {net_profit:.2f}€")
            
            if self._on_position_close:
                self._on_position_close(self, position)
            
            return net_profit
    
    def record_spin_off(self, amount: float):
        """Enregistre un spin-off (capital sorti)"""
        with self._lock:
            self._current_capital -= amount
            logger.info(f"🔄 Spin-off {self.id}: {amount:.2f}€ sortis, reste {self._current_capital:.2f}€")
    
    def activate_leverage(self, leverage: int) -> bool:
        """Active levier sur instance"""
        with self._lock:
            if self._current_capital >= 1000:
                self.config.leverage = leverage
                logger.info(f"⚡ Levier x{leverage} activé sur {self.id}")
                return True
            return False
    
    # Getters
    
    def get_current_capital(self) -> float:
        """Capital courant"""
        with self._lock:
            return self._current_capital
    
    def get_initial_capital(self) -> float:
        """Capital initial"""
        return self._initial_capital
    
    def get_profit(self) -> float:
        """Profit total"""
        return self._current_capital - self._initial_capital
    
    def get_win_streak(self) -> int:
        """Série de victoires"""
        return self._win_streak
    
    def get_drawdown(self) -> float:
        """Drawdown courant"""
        with self._lock:
            if self._peak_capital > 0:
                return (self._peak_capital - self._current_capital) / self._peak_capital
            return 0.0
    
    def get_max_drawdown(self) -> float:
        """Drawdown max historique"""
        return self._max_drawdown
    
    def get_volatility(self) -> float:
        """Calcule volatilité sur dernières 24h"""
        with self._lock:
            if len(self._price_history) < 2:
                return 0.0
            
            # Prend dernières 24h
            cutoff = datetime.now() - timedelta(hours=24)
            recent_prices = [p for t, p in self._price_history if t > cutoff]
            
            if len(recent_prices) < 2:
                return 0.0
            
            # Calcule std dev
            mean = sum(recent_prices) / len(recent_prices)
            variance = sum((p - mean) ** 2 for p in recent_prices) / len(recent_prices)
            std_dev = variance ** 0.5
            
            return std_dev / mean if mean > 0 else 0.0
    
    def detect_trend(self) -> str:
        """Détecte tendance actuelle"""
        with self._lock:
            if len(self._price_history) < 20:
                return "unknown"
            
            # Moyennes mobiles simples
            prices = [p for t, p in self._price_history[-50:]]
            
            if len(prices) < 20:
                return "unknown"
            
            ma_short = sum(prices[-10:]) / 10
            ma_long = sum(prices[-30:]) / 30
            
            threshold = 0.005  # 0.5%
            
            if ma_short > ma_long * (1 + threshold):
                return "up"
            elif ma_short < ma_long * (1 - threshold):
                return "down"
            else:
                return "range"
    
    def is_running(self) -> bool:
        """Vérifie si instance active"""
        return self.status == InstanceStatus.RUNNING
    
    def get_status(self) -> Dict[str, Any]:
        """Statut complet"""
        return {
            'id': self.id,
            'name': self.config.name,
            'status': self.status.value,
            'strategy': self.config.strategy,
            'capital_initial': self._initial_capital,
            'capital_current': self.get_current_capital(),
            'profit': self.get_profit(),
            'profit_pct': (self.get_profit() / self._initial_capital * 100),
            'win_streak': self._win_streak,
            'drawdown': self.get_drawdown(),
            'max_drawdown': self._max_drawdown,
            'positions_open': len([p for p in self._positions.values() if p.status == "open"]),
            'positions_closed': len([p for p in self._positions.values() if p.status == "closed"]),
            'leverage': self.config.leverage,
            'trend': self.detect_trend(),
            'last_price': self._last_price
        }
    
    # Méthodes privées
    
    def _cancel_all_orders(self):
        """Annule tous les ordres ouverts"""
        logger.info(f"🚫 Annulation ordres {self.id}")
        # TODO: Implémenter via API Kraken
    
    def _wait_positions_closed(self):
        """Attend fermeture positions"""
        timeout = 60  # 1 minute max
        start = time.time()
        
        while time.time() - start < timeout:
            with self._lock:
                open_count = len([p for p in self._positions.values() if p.status == "open"])
            
            if open_count == 0:
                break
            
            time.sleep(1)
    
    def _close_all_positions_market(self):
        """Ferme toutes positions au marché (urgence)"""
        logger.warning(f"🚨 Fermeture marché toutes positions {self.id}")
        # TODO: Implémenter ordres MARKET
