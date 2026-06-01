"""
AUTOBOT V2 - Full Auto Multi-Instance Trading Bot
Architecture modulaire avec orchestrateur et validation "voyants au vert"
"""

__version__ = "2.0.0"
__author__ = "AUTOBOT Team"

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

_LAZY_EXPORTS = {
    "Orchestrator": ("orchestrator", "Orchestrator"),
    "InstanceConfig": ("orchestrator", "InstanceConfig"),
    "TradingInstance": ("instance", "TradingInstance"),
    "InstanceStatus": ("instance", "InstanceStatus"),
    "ValidatorEngine": ("validator", "ValidatorEngine"),
    "ValidationResult": ("validator", "ValidationResult"),
    "ValidationStatus": ("validator", "ValidationStatus"),
    "DefaultValidators": ("validator", "DefaultValidators"),
    "RiskManager": ("risk_manager", "RiskManager"),
    "RiskConfig": ("risk_manager", "RiskConfig"),
    "KrakenWebSocket": ("websocket_client", "KrakenWebSocket"),
    "TickerData": ("websocket_client", "TickerData"),
    "SignalHandler": ("signal_handler", "SignalHandler"),
}


def __getattr__(name):
    """Keep runtime exports available without importing them during research tests."""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(f"{__name__}.{module_name}"), attr_name)
    globals()[name] = value
    return value
