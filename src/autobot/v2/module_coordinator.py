from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from time import perf_counter
from typing import Dict, List
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

    def _quick_ping(self, url: str, timeout: float = 1.5) -> bool:
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

    def module_record_failure(self, name: str) -> None:
        if name not in self._o._module_backoff:
            return
        failures = float(self._o._module_backoff[name].get("failures", 0.0)) + 1.0
        delay = min(2 ** min(int(failures), 8), MAX_BACKOFF_SECONDS)
        self._o._module_backoff[name]["failures"] = failures
        self._o._module_backoff[name]["next_retry_ts"] = perf_counter() + delay

    def validate_dependencies(self) -> Dict[str, List[str]]:
        enabled: List[str] = []
        disabled: List[str] = []

        if self._o.hardening_flags.get("enable_sentiment", False):
            sentiment_api_key = os.getenv("SENTIMENT_API_KEY", "").strip()
            twitter_ok = self._quick_ping("https://api.twitter.com")
            reddit_ok = self._quick_ping("https://www.reddit.com")
            if not sentiment_api_key or not twitter_ok or not reddit_ok:
                logger.warning("SentimentNLP désactivé - clé API manquante")
                self._o.hardening_flags["enable_sentiment"] = False
                disabled.append("sentiment")
            else:
                logger.info("✅ SentimentNLP dépendances OK")
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
                disabled.append("xgboost")
            else:
                logger.info("✅ XGBoost dépendances OK")
                self._o.hardening_flags["enable_xgboost"] = True
                self._o.hardening_flags["enable_ml"] = True
                enabled.append("xgboost")
        else:
            logger.info("ℹ️ XGBoost non activé")
            disabled.append("xgboost")

        if self._o.hardening_flags.get("enable_onchain", False):
            onchain_api_key = os.getenv("ONCHAIN_API_KEY", "").strip()
            node_url = os.getenv("ONCHAIN_NODE_URL", "https://api.blockchain.info")
            if not onchain_api_key or not self._quick_ping(node_url):
                logger.warning("OnChain désactivé")
                self._o.hardening_flags["enable_onchain"] = False
                disabled.append("onchain")
            else:
                logger.info("✅ OnChain dépendances OK")
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
                disabled.append("shadow_trading")
                raise RuntimeError("Shadow trading impossible")
            logger.info("✅ Shadow trading dépendances OK")
            enabled.append("shadow_trading")
        else:
            logger.info("ℹ️ Shadow trading non activé")
            disabled.append("shadow_trading")

        report = {"enabled": enabled, "disabled": disabled}
        self._o._dependency_report = report
        return report
