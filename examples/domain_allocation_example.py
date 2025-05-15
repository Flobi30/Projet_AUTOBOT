"""
Example of using the specialized domain allocation strategy with ghosting manager.

This example demonstrates how to configure and use the specialized domain allocation
strategy to efficiently scale AUTOBOT to hundreds/thousands of instances across
different domains like trading, e-commerce, and arbitrage.
"""

import os
import logging
import time
from typing import Dict, Any

from autobot.autobot_security.license_manager import LicenseManager
from autobot.trading.ghosting_manager import GhostingManager, GhostingMode
from autobot.trading.domain_allocation import DomainAllocationStrategy, DomainAllocationIntegration

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """
    Main function demonstrating specialized domain allocation.
    """
    license_manager = LicenseManager(
        license_key="YOUR_LICENSE_KEY",
        max_instances=1000  # Allow up to 1000 instances
    )
    
    specialized_domains = {
        "trading": 600,      # 60% for trading
        "ecommerce": 200,    # 20% for e-commerce
        "arbitrage": 200     # 20% for arbitrage
    }
    
    domain_strategy = DomainAllocationStrategy(
        domain_limits=specialized_domains,
        domain_priorities={
            "trading": 3,     # Highest priority
            "arbitrage": 2,   # Medium priority
            "ecommerce": 1    # Lowest priority
        }
    )
    
    domain_integration = DomainAllocationIntegration(domain_strategy)
    
    ghosting_manager = GhostingManager(
        license_manager=license_manager,
        max_instances=1000,
        default_mode=GhostingMode.ACTIVE,  # Always use ACTIVE mode for security
        specialized_domains=specialized_domains
    )
    
    for _ in range(10):
        domain = domain_integration.allocate_domain_for_instance()
        
        if domain:
            logger.info(f"Created new instance in domain: {domain}")
            
        else:
            logger.warning("Failed to allocate domain for new instance")
    
    stats = domain_integration.get_domain_stats()
    logger.info(f"Domain allocation statistics: {stats}")
    

if __name__ == "__main__":
    main()
