from __future__ import annotations

import logging
import os
import socket
import ssl
import shutil
from http.client import HTTPSConnection
from ipaddress import ip_address
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Set
from urllib.parse import urlparse

from .config import MAX_BACKOFF_SECONDS

logger = logging.getLogger(__name__)


class _PinnedIPHTTPSConnection(HTTPSConnection):
    """HTTPS connection pinned to a resolved IP while preserving TLS host/SNI."""

    def __init__(self, host: str, target_ip: str, timeout: float) -> None:
        super().__init__(host=host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._target_ip = target_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._target_ip, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


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

    def _resolve_allowed_ping_ips(
        self,
        url: str,
        module: str = "dependency",
        endpoint_name: str = "endpoint",
    ) -> tuple[str, Set[str], str] | None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            self._reject_ping_url(module, endpoint_name, url, "non_https_scheme")
            return None

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            self._reject_ping_url(module, endpoint_name, url, "missing_hostname")
            return None

        allowlist = self._get_allowed_ping_hosts()
        if hostname not in allowlist:
            self._reject_ping_url(module, endpoint_name, url, f"host_not_allowlisted:{hostname}")
            return None

        try:
            host_ip = ip_address(hostname)
            if host_ip.is_private or host_ip.is_loopback or host_ip.is_link_local:
                self._reject_ping_url(module, endpoint_name, url, "forbidden_ip_literal")
                return None
        except ValueError:
            pass

        try:
            addr_info = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except Exception:
            self._reject_ping_url(module, endpoint_name, url, "dns_resolution_failed")
            return None

        allowed_ips: Set[str] = set()
        selected_ip: str | None = None
        for addr in addr_info:
            resolved_ip = ip_address(addr[4][0])
            if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                self._reject_ping_url(module, endpoint_name, url, f"forbidden_resolved_ip:{resolved_ip}")
                return None
            resolved_ip_str = str(resolved_ip)
            allowed_ips.add(resolved_ip_str)
            if selected_ip is None:
                selected_ip = resolved_ip_str
        if not allowed_ips or selected_ip is None:
            self._reject_ping_url(module, endpoint_name, url, "no_valid_resolved_ip")
            return None
        return hostname, allowed_ips, selected_ip

    def _resolve_allowed_ping_ip(self, hostname: str) -> Optional[str]:
        try:
            addr_info = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except Exception:
            return None
        for addr in addr_info:
            candidate_ip = addr[4][0]
            parsed_ip = ip_address(candidate_ip)
            if parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local:
                continue
            return candidate_ip
        return None

    def _is_allowed_remote_ip(self, ip_value: str) -> bool:
        try:
            remote_ip = ip_address(ip_value)
        except ValueError:
            return False
        return not (remote_ip.is_private or remote_ip.is_loopback or remote_ip.is_link_local)

    def _quick_ping_with_pinned_ip(
        self,
        hostname: str,
        request_target: str,
        timeout: float,
        port: int = 443,
    ) -> bool:
        target_ip = self._resolve_allowed_ping_ip(hostname)
        if not target_ip:
            return False

        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        try:
            with socket.create_connection((target_ip, port), timeout=timeout) as tcp_sock:
                with context.wrap_socket(tcp_sock, server_hostname=hostname) as tls_sock:
                    tls_sock.settimeout(timeout)
                    remote_peer = tls_sock.getpeername()[0]
                    if remote_peer != target_ip or not self._is_allowed_remote_ip(remote_peer):
                        return False
                    request_data = (
                        f"HEAD {request_target} HTTP/1.1\r\n"
                        f"Host: {hostname}\r\n"
                        "Connection: close\r\n"
                        "User-Agent: AutobotHealthcheck/1.0\r\n\r\n"
                    ).encode("ascii", errors="ignore")
                    tls_sock.sendall(request_data)
                    first_line = b""
                    while not first_line.endswith(b"\r\n"):
                        chunk = tls_sock.recv(1)
                        if not chunk:
                            break
                        first_line += chunk

            if not first_line:
                return False
            status_parts = first_line.decode("iso-8859-1", errors="replace").strip().split(" ")
            if len(status_parts) < 2:
                return False
            status_code = int(status_parts[1])
            return status_code < 500
        except Exception:
            return False

    def _quick_ping(
        self,
        url: str,
        timeout: float = 1.5,
        module: str = "dependency",
        endpoint_name: str = "endpoint",
    ) -> bool:
        resolved = self._resolve_allowed_ping_ips(url, module=module, endpoint_name=endpoint_name)
        if not resolved:
            return False
        parsed = urlparse(url)
        request_path = parsed.path or "/"
        if parsed.query:
            request_path = f"{request_path}?{parsed.query}"
        hostname, allowed_ips, target_ip = resolved
        try:
            conn = _PinnedIPHTTPSConnection(host=hostname, target_ip=target_ip, timeout=timeout)
            conn.request("HEAD", request_path, headers={"Host": hostname})
            peer_ip = conn.sock.getpeername()[0] if conn.sock else ""
            if peer_ip and peer_ip != target_ip:
                logger.warning(
                    "Divergence IP/hostname détectée pour _quick_ping (%s): host=%s expected_ip=%s actual_ip=%s",
                    endpoint_name,
                    hostname,
                    target_ip,
                    peer_ip,
                )
            if peer_ip not in allowed_ips:
                self._reject_ping_url(
                    module,
                    endpoint_name,
                    url,
                    f"post_connect_ip_not_allowlisted:{peer_ip or 'unknown'}",
                )
                conn.close()
                return False
            resp = conn.getresponse()
            status_ok = int(getattr(resp, "status", 200)) < 500
            conn.close()
            return status_ok
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
