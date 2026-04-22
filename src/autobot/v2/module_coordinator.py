from __future__ import annotations

import logging
import os
import socket
import shutil
from ipaddress import ip_address
from pathlib import Path
from time import perf_counter
from typing import Dict, List
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


class ModuleCoordinator:
    """Coordinates module lifecycle, dependency checks and backoff policies."""

    def __init__(self, orchestrator: object) -> None:
        self._o = orchestrator

    def initialize_modules(self) -> None:
        """Initialize optional modules through ModuleManager and orchestrator hooks."""
        self._o.module_manager.init_modules(self._o)
        self._o._reuse_module_manager_instances()
        self._o.shadow_manager = self._o._init_shadow_manager()
        self._o._rebalance_manager = self._o._init_rebalance_manager()
        self._o._auto_evolution_manager = self._o._init_auto_evolution_manager()

    def _get_allowed_ping_hosts(self) -> set[str]:
        raw_allowlist = os.getenv(
            "PING_HOST_ALLOWLIST",
            "api.twitter.com,www.reddit.com,api.blockchain.info",
        )
        return {host.strip().lower() for host in raw_allowlist.split(",") if host.strip()}

    def _reject_ping_url(self, module: str, endpoint_name: str, url: str, reason: str) -> bool:
        logger.warning("URL rejetée pour _quick_ping (%s): %s [%s]", endpoint_name, url, reason)
        if hasattr(self._o, "_record_module_event"):
            self._o._record_module_event(module, "warning", f"url_rejected:{endpoint_name}:{reason}")
        return False

    def _validate_ping_url(
        self,
        url: str,
        module: str = "dependency",
        endpoint_name: str = "endpoint",
    ) -> bool:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return self._reject_ping_url(module, endpoint_name, url, "non_https_scheme")

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return self._reject_ping_url(module, endpoint_name, url, "missing_hostname")

        allowlist = self._get_allowed_ping_hosts()
        if hostname not in allowlist:
            return self._reject_ping_url(module, endpoint_name, url, f"host_not_allowlisted:{hostname}")

        try:
            host_ip = ip_address(hostname)
            if host_ip.is_private or host_ip.is_loopback or host_ip.is_link_local:
                return self._reject_ping_url(module, endpoint_name, url, "forbidden_ip_literal")
        except ValueError:
            pass

        try:
            addr_info = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except Exception:
            return self._reject_ping_url(module, endpoint_name, url, "dns_resolution_failed")

        for addr in addr_info:
            resolved_ip = ip_address(addr[4][0])
            if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                return self._reject_ping_url(module, endpoint_name, url, f"forbidden_resolved_ip:{resolved_ip}")
        return True

    def _quick_ping(
        self,
        url: str,
        timeout: float = 1.5,
        module: str = "dependency",
        endpoint_name: str = "endpoint",
    ) -> bool:
        if not self._validate_ping_url(url, module=module, endpoint_name=endpoint_name):
            return False
        try:
            req = Request(url, method="HEAD")
            with urlopen(req, timeout=timeout) as resp:
                return int(getattr(resp, "status", 200)) < 500
        except Exception:
            return False

    def module_can_run(self, name: str) -> bool:
        info = self._o._module_backoff.get(name)
        if not info:
            return True
        return perf_counter() >= float(info.get("next_retry_ts", 0.0))

    def module_record_success(self, name: str) -> None:
        if name not in self._o._module_backoff:
            return
        self._o._module_backoff[name]["failures"] = 0.0
        self._o._module_backoff[name]["next_retry_ts"] = 0.0
        self._o._record_module_event(name, "ok")

    def module_record_failure(self, name: str) -> None:
        if name not in self._o._module_backoff:
            return
        failures = float(self._o._module_backoff[name].get("failures", 0.0)) + 1.0
        delay = min(2 ** min(int(failures), 8), MAX_BACKOFF_SECONDS)
        self._o._module_backoff[name]["failures"] = failures
        self._o._module_backoff[name]["next_retry_ts"] = perf_counter() + delay
        self._o._record_module_event(name, "error", f"backoff_delay={delay}s failures={failures}")

    def validate_dependencies(self) -> Dict[str, List[str]]:
        enabled: List[str] = []
        disabled: List[str] = []

        if self._o.hardening_flags.get("enable_sentiment", False):
            sentiment_api_key = os.getenv("SENTIMENT_API_KEY", "").strip()
            twitter_ok = self._quick_ping(
                "https://api.twitter.com",
                module="sentiment",
                endpoint_name="twitter_api",
            )
            reddit_ok = self._quick_ping(
                "https://www.reddit.com",
                module="sentiment",
                endpoint_name="reddit_api",
            )
            if not sentiment_api_key or not twitter_ok or not reddit_ok:
                logger.warning("SentimentNLP désactivé - clé API manquante")
                self._o.hardening_flags["enable_sentiment"] = False
                self._o._record_module_event("sentiment", "warning", "missing_api_or_unreachable")
                disabled.append("sentiment")
            else:
                logger.info("✅ SentimentNLP dépendances OK")
                self._o._record_module_event("sentiment", "ok")
                enabled.append("sentiment")
        else:
            logger.info("ℹ️ SentimentNLP non activé")
            disabled.append("sentiment")

        xgb_requested = (
            self._o.hardening_flags.get("enable_xgboost", False)
            or self._o.hardening_flags.get("enable_ml", False)
        )
        if xgb_requested:
            model_path = Path(os.getenv("XGBOOST_MODEL_PATH", "models/xgboost.pkl"))
            features_path = Path(os.getenv("HISTORICAL_DATA_PATH", "data/historical"))
            features_available = features_path.exists() and features_path.is_dir() and any(features_path.iterdir())
            if not model_path.exists() or not features_available:
                logger.warning("XGBoost désactivé - modèle non entraîné")
                self._o.hardening_flags["enable_xgboost"] = False
                self._o.hardening_flags["enable_ml"] = False
                self._o._record_module_event("xgboost", "warning", "model_or_features_missing")
                disabled.append("xgboost")
            else:
                logger.info("✅ XGBoost dépendances OK")
                self._o.hardening_flags["enable_xgboost"] = True
                self._o.hardening_flags["enable_ml"] = True
                self._o._record_module_event("xgboost", "ok")
                enabled.append("xgboost")
        else:
            logger.info("ℹ️ XGBoost non activé")
            disabled.append("xgboost")

        if self._o.hardening_flags.get("enable_onchain", False):
            onchain_api_key = os.getenv("ONCHAIN_API_KEY", "").strip()
            node_url = os.getenv("ONCHAIN_NODE_URL", "https://api.blockchain.info")
            if not onchain_api_key or not self._quick_ping(
                node_url,
                module="onchain",
                endpoint_name="onchain_node_url",
            ):
                logger.warning("OnChain désactivé")
                self._o.hardening_flags["enable_onchain"] = False
                self._o._record_module_event("onchain", "warning", "missing_api_or_node_unreachable")
                disabled.append("onchain")
            else:
                logger.info("✅ OnChain dépendances OK")
                self._o._record_module_event("onchain", "ok")
                enabled.append("onchain")
        else:
            logger.info("ℹ️ OnChain non activé")
            disabled.append("onchain")

        if self._o.hardening_flags.get("enable_shadow_trading", False):
            db_path = Path(os.getenv("SHADOW_TRADING_DB_PATH", "data/shadow_trading.db"))
            parent = db_path.parent
            db_accessible = parent.exists() and os.access(parent, os.W_OK)
            try:
                free_bytes = shutil.disk_usage(parent if parent.exists() else Path(".")).free
            except Exception:
                free_bytes = 0
            if not db_accessible or free_bytes < 50 * 1024 * 1024:
                logger.error("Shadow trading impossible")
                self._o.hardening_flags["enable_shadow_trading"] = False
                self._o._record_module_event("shadow_trading", "error", "db_unreachable_or_low_disk")
                disabled.append("shadow_trading")
                raise RuntimeError("Shadow trading impossible")
            logger.info("✅ Shadow trading dépendances OK")
            self._o._record_module_event("shadow_trading", "ok")
            enabled.append("shadow_trading")
        else:
            logger.info("ℹ️ Shadow trading non activé")
            disabled.append("shadow_trading")

        report = {"enabled": enabled, "disabled": disabled}
        self._o._dependency_report = report
        return report
