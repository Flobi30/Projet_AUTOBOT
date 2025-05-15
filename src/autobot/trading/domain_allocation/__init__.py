"""
Domain Allocation Package for AUTOBOT

This package provides specialized domain allocation strategies for efficient
scaling to hundreds/thousands of instances across different domains like
trading, e-commerce, and arbitrage.
"""

from .strategy import (
    DomainAllocationStrategy
)

from .integration import (
    DomainAllocationIntegration
)

__all__ = [
    'DomainAllocationStrategy',
    'DomainAllocationIntegration'
]
