"""Passive reconciliation-domain contracts shared by runtime implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Divergence:
    type: str
    position_id: Optional[str]
    kraken_txid: Optional[str]
    details: dict[str, Any]
    severity: str

