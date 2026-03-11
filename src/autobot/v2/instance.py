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
from collections import deque

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
        # CORRECTION: Utiliser deque pour éviter fuite mémoire
        self._max_trades_history = 1000
        self._trades: deque = deque(maxlen=self._max_trades_history)
        self._open_orders: Dict[str, Any] = {}
        
        # Performance
        self._win_count = 0
        self._loss_count = 0
        self._win_streak = 0
        self._max_drawdown = 0.0
        self._peak_capital = config.initial_capital
        
        # Prix
        self._last_price: Optional[float] = None
        # CORRECTION: Utiliser deque pour performance O(1)
        self._max_history_size = 1000
        self._price_history: deque = deque(maxlen=self._max_history_size)
        
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
        
        # CORRECTION: Modifier status sous lock
        with self._lock:
            self.status = InstanceStatus.STOPPED
        
        # Ferme tout immédiatement (market orders)
        self._close_all_positions_market()
    
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
            # CORRECTION: deque gère auto la taille max
        
        # Notifie stratégie
        if self._strategy and self.status == InstanceStatus.RUNNING:
            self._strategy.on_price(data.price)
    
    def open_position(self, price: float, volume: float) -> Optional[Position]:
        """Ouvre une position (vérification et exécution atomiques)"""
        order_value = price * volume
        
        # CORRECTION: Tout dans un seul lock pour éviter TOCTOU
        with self._lock:
            # Vérifications
            available = self._current_capital - self._allocated_capital
            max_positions = 10
            
            if not (
                self.status == InstanceStatus.RUNNING and
                available >= order_value and
                len(self._positions) < max_positions
            ):
                return None
            
            # Crée la position
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
            
            # CORRECTION: Frais calculés séparément (maker 0.16%, taker 0.26%)
            buy_fee = position.buy_price * position.volume * 0.0016   # Maker
            sell_fee = sell_price * position.volume * 0.0026         # Taker
            fees = buy_fee + sell_fee
            
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
        # CORRECTION: Utiliser get_current_capital() pour cohérence (avec lock)
        return self.get_current_capital() - self._initial_capital
    
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
        cutoff = datetime.now() - timedelta(hours=24)
        
        # CORRECTION: Copier données sous lock, calculer hors lock
        with self._lock:
            if len(self._price_history) < 2:
                return 0.0
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
        # CORRECTION: Copier données sous lock, calculer hors lock
        with self._lock:
            if len(self._price_history) < 20:
                return "unknown"
            prices = [p for t, p in self._price_history]
        
        if len(prices) < 20:
            return "unknown"
        
        # CORRECTION: Diviser par le nombre réel d'éléments, pas 30
        ma_short = sum(prices[-10:]) / min(10, len(prices[-10:]))
        ma_long = sum(prices[-30:]) / min(30, len(prices[-30:]))
        
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
        """Statut complet - CORRECTION: Thread-safe"""
        with self._lock:
            positions_copy = list(self._positions.values())

        return {
            'id': self.id,
            'name': self.config.name,
            'status': self.status.value,
            'strategy': self.config.strategy,
            'initial_capital': self._initial_capital,
            'current_capital': self.get_current_capital(),
            'total_profit': self.get_profit(),
            'profit_pct': (self.get_profit() / self._initial_capital * 100),
            'win_streak': self._win_streak,
            'drawdown': self.get_drawdown(),
            'max_drawdown': self._max_drawdown,
            'positions': positions_copy,
            'open_positions_count': len([p for p in positions_copy if p.status == "open"]),
            'closed_positions_count': len([p for p in positions_copy if p.status == "closed"]),
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

    # =========================================================================
    # CORRECTION: Méthodes thread-safe pour l'API Dashboard
    # =========================================================================

    def get_positions_snapshot(self) -> List[Dict]:
        """
        CORRECTION: Version thread-safe pour l'API.
        Retourne une copie des positions (pas d'accès direct à _positions).
        """
        with self._lock:
            positions_copy = list(self._positions.items())
            last_price = self._last_price

        snapshot = []
        for pos_id, pos in positions_copy:
            current_price = last_price or pos.buy_price
            pnl = (current_price - pos.buy_price) * pos.volume
            pnl_pct = (current_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

            snapshot.append({
                'id': pos_id,
                'pair': self.config.symbol,
                'side': 'LONG',
                'size': f"{pos.volume:.6f}",
                'entry_price': pos.buy_price,
                'current_price': current_price,
                'pnl': pnl,
                'pnl_percent': pnl_pct
            })

        return snapshot
