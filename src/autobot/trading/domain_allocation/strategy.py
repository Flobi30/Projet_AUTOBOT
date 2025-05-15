"""
Specialized Domain Allocation Strategy for AUTOBOT

This module implements the specialized domain allocation strategy for efficient
scaling to hundreds/thousands of instances across different domains like trading,
e-commerce, and arbitrage.
"""

import logging
import threading
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class DomainAllocationStrategy:
    """
    Specialized domain allocation strategy for efficient scaling.
    
    This class manages the allocation of instances across different specialized
    domains like trading, e-commerce, and arbitrage, ensuring optimal resource
    utilization and performance.
    """
    
    def __init__(
        self,
        domain_limits: Dict[str, int],
        domain_priorities: Optional[Dict[str, int]] = None
    ):
        """
        Initialize the domain allocation strategy.
        
        Args:
            domain_limits: Dictionary mapping domain names to maximum instance counts
                          (e.g., {"trading": 300, "ecommerce": 100, "arbitrage": 100})
            domain_priorities: Optional dictionary mapping domain names to priority levels
                              (higher values indicate higher priority)
        """
        self.domain_limits = domain_limits
        self.domain_priorities = domain_priorities or {
            domain: idx for idx, domain in enumerate(domain_limits.keys())
        }
        
        self.domain_counts = {domain: 0 for domain in domain_limits}
        self.domain_locks = {domain: threading.Lock() for domain in domain_limits}
        
        self.total_limit = sum(domain_limits.values())
        self.total_count = 0
        
        logger.info(f"Initialized domain allocation strategy with limits: {domain_limits}")
    
    def allocate_domain(self, preferred_domain: Optional[str] = None) -> Optional[str]:
        """
        Allocate a domain for a new instance.
        
        Args:
            preferred_domain: Optional preferred domain for the new instance
            
        Returns:
            str: Allocated domain name, or None if allocation failed
        """
        if preferred_domain and preferred_domain in self.domain_limits:
            with self.domain_locks[preferred_domain]:
                if self.domain_counts[preferred_domain] < self.domain_limits[preferred_domain]:
                    self.domain_counts[preferred_domain] += 1
                    self.total_count += 1
                    logger.debug(f"Allocated preferred domain: {preferred_domain}")
                    return preferred_domain
        
        available_domains = []
        
        for domain, limit in self.domain_limits.items():
            with self.domain_locks[domain]:
                if self.domain_counts[domain] < limit:
                    available_domains.append((domain, self.domain_priorities.get(domain, 0)))
        
        if not available_domains:
            logger.warning("No domains available for allocation")
            return None
        
        available_domains.sort(key=lambda x: x[1], reverse=True)
        
        allocated_domain = available_domains[0][0]
        
        with self.domain_locks[allocated_domain]:
            self.domain_counts[allocated_domain] += 1
            self.total_count += 1
        
        logger.debug(f"Allocated domain: {allocated_domain}")
        return allocated_domain
    
    def release_domain(self, domain: str) -> bool:
        """
        Release a domain allocation.
        
        Args:
            domain: Domain to release
            
        Returns:
            bool: True if release was successful
        """
        if domain not in self.domain_limits:
            logger.warning(f"Unknown domain: {domain}")
            return False
        
        with self.domain_locks[domain]:
            if self.domain_counts[domain] > 0:
                self.domain_counts[domain] -= 1
                self.total_count -= 1
                logger.debug(f"Released domain: {domain}")
                return True
            else:
                logger.warning(f"Domain {domain} has no allocations to release")
                return False
    
    def get_domain_stats(self) -> Dict[str, Any]:
        """
        Get statistics about domain allocations.
        
        Returns:
            Dict: Domain allocation statistics
        """
        stats = {
            "total_limit": self.total_limit,
            "total_allocated": self.total_count,
            "domains": {}
        }
        
        for domain, limit in self.domain_limits.items():
            with self.domain_locks[domain]:
                count = self.domain_counts[domain]
                stats["domains"][domain] = {
                    "limit": limit,
                    "allocated": count,
                    "available": limit - count,
                    "utilization": count / limit if limit > 0 else 0
                }
        
        return stats
    
    def is_domain_available(self, domain: str) -> bool:
        """
        Check if a domain has available capacity.
        
        Args:
            domain: Domain to check
            
        Returns:
            bool: True if domain has available capacity
        """
        if domain not in self.domain_limits:
            return False
        
        with self.domain_locks[domain]:
            return self.domain_counts[domain] < self.domain_limits[domain]
    
    def get_available_domains(self) -> List[str]:
        """
        Get a list of domains with available capacity.
        
        Returns:
            List[str]: List of domain names with available capacity
        """
        available = []
        
        for domain, limit in self.domain_limits.items():
            with self.domain_locks[domain]:
                if self.domain_counts[domain] < limit:
                    available.append(domain)
        
        return available
