"""
Diagnostic API Endpoint — AutoBot V2

Endpoint /diagnostic pour voir l'état de santé complet du système.
Intégré dans le dashboard API existant.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .diagnostic_manager import get_diagnostic_manager, HealthStatus

logger = logging.getLogger(__name__)


class DiagnosticEndpoint:
    """
    Endpoint API pour le diagnostic.
    
    Routes:
        GET /diagnostic         → Statut complet
        GET /diagnostic/summary → Résumé textuel
        GET /diagnostic/health  → Health check simple (ok/warning/critical)
    """
    
    def __init__(self):
        self.diag = get_diagnostic_manager()
    
    async def get_full_diagnostic(self) -> Dict[str, Any]:
        """Retourne le diagnostic complet en JSON."""
        status = await self.diag.run_full_check()
        return self._status_to_dict(status)
    
    async def get_summary(self) -> str:
        """Retourne un résumé textuel."""
        status = await self.diag.run_full_check()
        return self.diag.get_summary_text()
    
    async def get_health(self) -> Dict[str, str]:
        """Health check simple pour monitoring externe."""
        status = await self.diag.run_full_check()
        return {
            "status": status.overall,
            "timestamp": status.timestamp.isoformat(),
            "issues_count": str(len(status.issues))
        }
    
    def _status_to_dict(self, status: HealthStatus) -> Dict[str, Any]:
        """Convertit HealthStatus en dict JSON."""
        return {
            "timestamp": status.timestamp.isoformat(),
            "overall": status.overall,
            "docker": status.docker,
            "system": status.system,
            "network": status.network,
            "kraken": status.kraken,
            "database": status.database,
            "bot": status.bot,
            "issues": status.issues,
            "recommendations": status.recommendations
        }


# Instance singleton
_diagnostic_endpoint: DiagnosticEndpoint = None


def get_diagnostic_endpoint() -> DiagnosticEndpoint:
    """Retourne l'instance singleton."""
    global _diagnostic_endpoint
    if _diagnostic_endpoint is None:
        _diagnostic_endpoint = DiagnosticEndpoint()
    return _diagnostic_endpoint
