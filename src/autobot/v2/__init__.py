"""
AUTOBOT V2 - Full Auto Multi-Instance Trading Bot
Architecture modulaire avec orchestrateur et validation "voyants au vert"
"""

__version__ = "2.0.0"
__author__ = "AUTOBOT Team"

from .orchestrator import Orchestrator, InstanceConfig
from .instance import TradingInstance, InstanceStatus
from .validator import ValidatorEngine, ValidationResult, ValidationStatus, DefaultValidators
from .risk_manager import RiskManager, RiskConfig
from .websocket_client import KrakenWebSocket, TickerData
from .signal_handler import SignalHandler

__all__ = [
    'Orchestrator',
    'InstanceConfig',
    'TradingInstance',
    'InstanceStatus',
    'ValidatorEngine',
    'ValidationResult',
    'ValidationStatus',
    'DefaultValidators',
    'RiskManager',
    'RiskConfig',
    'KrakenWebSocket',
    'TickerData',
    'SignalHandler'
]
