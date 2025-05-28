"""
Domain Allocation Integration for AUTOBOT

This module integrates the specialized domain allocation strategy with the
ghosting manager to enable efficient scaling to hundreds/thousands of instances.
"""

import os
import logging
from typing import Dict, Any, Optional, List

from ..domain_allocation.strategy import DomainAllocationStrategy

logger = logging.getLogger(__name__)

class DomainAllocationIntegration:
    """
    Integration between domain allocation strategy and ghosting manager.
    
    This class provides methods to integrate the domain allocation strategy
    with the ghosting manager, enabling efficient scaling to hundreds/thousands
    of instances across different specialized domains.
    """
    
    def __init__(self, domain_strategy: DomainAllocationStrategy):
        """
        Initialize the domain allocation integration.
        
        Args:
            domain_strategy: Domain allocation strategy instance
        """
        self.domain_strategy = domain_strategy
        logger.info("Domain allocation integration initialized")
    
    def allocate_domain_for_instance(self, preferred_domain: Optional[str] = None) -> Optional[str]:
        """
        Allocate a domain for a new instance.
        
        Args:
            preferred_domain: Optional preferred domain for the new instance
            
        Returns:
            str: Allocated domain name, or None if allocation failed
        """
        return self.domain_strategy.allocate_domain(preferred_domain)
    
    def release_domain_for_instance(self, domain: str) -> bool:
        """
        Release a domain allocation for an instance.
        
        Args:
            domain: Domain to release
            
        Returns:
            bool: True if release was successful
        """
        return self.domain_strategy.release_domain(domain)
    
    def get_domain_stats(self) -> Dict[str, Any]:
        """
        Get statistics about domain allocations.
        
        Returns:
            Dict: Domain allocation statistics
        """
        return self.domain_strategy.get_domain_stats()
    
    def get_available_domains(self) -> List[str]:
        """
        Get a list of domains with available capacity.
        
        Returns:
            List[str]: List of domain names with available capacity
        """
        return self.domain_strategy.get_available_domains()
    
    def is_domain_available(self, domain: str) -> bool:
        """
        Check if a domain has available capacity.
        
        Args:
            domain: Domain to check
            
        Returns:
            bool: True if domain has available capacity
        """
        return self.domain_strategy.is_domain_available(domain)
