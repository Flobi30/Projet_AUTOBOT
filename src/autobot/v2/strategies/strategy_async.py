"""
Strategy Base — Async version
MIGRATION P0: Replaces Strategy base class (threading.RLock → no lock needed in single-threaded async)

In asyncio, on_price() is called sequentially from the event loop,
so no lock is needed for the strategy's internal state.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, Optional

from . import TradingSignal, SignalType

logger = logging.getLogger(__name__)

# Async callback type
AsyncSignalCallback = Callable[[TradingSignal], Coroutine[Any, Any, None]]


class StrategyAsync(ABC):
    """
    Async base class for all strategies.

    Key difference from sync Strategy:
    - No threading.RLock (single-threaded event loop)
    - Signal callback can be sync or async
    - on_price() is sync (CPU-bound; called from async context)
    """

    def __init__(self, instance: Any, config: Optional[Dict] = None) -> None:
        self.instance = instance
        self.config = config or {}
        self.name = self.__class__.__name__

        self._on_signal: Optional[Callable] = None
        self._initialized = False
        self._last_signal_times: Dict[str, datetime] = {}
        self._signal_cooldown_seconds: int = self.config.get("signal_cooldown", 30)

        logger.info(f"🎯 Stratégie {self.name} initialisée (async)")

    def set_signal_callback(self, callback: Callable) -> None:
        self._on_signal = callback

    @abstractmethod
    def on_price(self, price: float) -> None:
        """Called on each price update. CPU-bound, no I/O."""
        pass

    @abstractmethod
    def on_position_opened(self, position: Any) -> None:
        pass

    @abstractmethod
    def on_position_closed(self, position: Any, profit: float) -> None:
        pass

    def emit_signal(self, signal: TradingSignal, bypass_cooldown: bool = False) -> None:
        """Emit a trading signal."""
        key = signal.type.value
        if not bypass_cooldown:
            last = self._last_signal_times.get(key)
            if last:
                elapsed = (datetime.now() - last).total_seconds()
                if elapsed < self._signal_cooldown_seconds:
                    return

        self._last_signal_times[key] = datetime.now()
        logger.info(f"📡 Signal {key.upper()}: {signal.reason} @ {signal.price:.2f}")

        if self._on_signal:
            try:
                self._on_signal(signal)
            except Exception as exc:
                logger.exception(f"❌ Erreur callback signal: {exc}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "initialized": self._initialized,
            "last_signals": {k: v.isoformat() for k, v in self._last_signal_times.items()},
            "config": self.config,
        }

    def reset(self) -> None:
        self._initialized = False
        self._last_signal_times.clear()
