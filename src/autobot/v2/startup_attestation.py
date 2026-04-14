from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import aiohttp

from .kill_switch import KillSwitch
from .order_executor_async import OrderExecutorAsync
from .reconciliation_strict import StrictReconciliation

logger = logging.getLogger(__name__)


class StartupAttestationError(RuntimeError):
    pass


@dataclass
class StartupAttestationResult:
    ok: bool
    checks: Dict[str, bool]
    reasons: list[str]


class StartupAttestation:
    VALID_ENVS = {"development", "staging", "production"}
    VALID_STAGES = {"paper", "micro_live", "small_live"}
    COMPROMISED_FINGERPRINTS = {
        "compromised_autobot_key_v1",
        "flobi30_autobot_leak_2026",
    }

    def __init__(
        self,
        order_executor: Optional[OrderExecutorAsync],
        kill_switch: Optional[KillSwitch],
        app_env: Optional[str] = None,
    ) -> None:
        self.order_executor = order_executor
        self.kill_switch = kill_switch
        self.app_env = (app_env or os.getenv("APP_ENV", "production")).lower().strip()
        self.reconciler = StrictReconciliation()

    async def run(self, preflight_only: bool = False) -> StartupAttestationResult:
        checks: Dict[str, bool] = {}
        reasons: list[str] = []

        def fail(name: str, reason: str) -> None:
            checks[name] = False
            reasons.append(reason)

        # 1) APP_ENV validity
        checks["app_env_valid"] = self.app_env in self.VALID_ENVS
        if not checks["app_env_valid"]:
            fail("app_env_valid", f"APP_ENV invalide: {self.app_env}")

        paper_mode = os.getenv("PAPER_TRADING", "false").lower() == "true"
        stage = os.getenv("DEPLOYMENT_STAGE", "paper").strip().lower()
        checks["deployment_stage_valid"] = stage in self.VALID_STAGES
        if not checks["deployment_stage_valid"]:
            fail("deployment_stage_valid", f"DEPLOYMENT_STAGE invalide: {stage}")
        # 2) live confirmation gate
        checks["live_confirmation"] = paper_mode or os.getenv("LIVE_TRADING_CONFIRMATION", "false").lower() == "true"
        if not checks["live_confirmation"]:
            fail("live_confirmation", "LIVE mode sans LIVE_TRADING_CONFIRMATION=true")

        # 3) auth token present
        checks["dashboard_token"] = bool(os.getenv("DASHBOARD_API_TOKEN", "").strip())
        if not checks["dashboard_token"]:
            fail("dashboard_token", "DASHBOARD_API_TOKEN manquant")

        # 4) required risk limits present
        risk_required = ["MAX_DRAWDOWN_PCT", "RISK_PER_TRADE_PCT", "MAX_POSITION_SIZE_PCT"]
        checks["risk_limits"] = all(os.getenv(k) not in (None, "") for k in risk_required)
        if not checks["risk_limits"]:
            fail("risk_limits", f"Risk limits manquants: {[k for k in risk_required if os.getenv(k) in (None, '')]}")

        # 5) kill switch initialized
        checks["kill_switch_initialized"] = self.kill_switch is not None
        if not checks["kill_switch_initialized"]:
            fail("kill_switch_initialized", "Kill switch non initialisé")
        checks["global_kill_switch_clear"] = self._check_global_kill_switch_clear()
        if not checks["global_kill_switch_clear"]:
            fail("global_kill_switch_clear", "Global kill switch persisté actif/incohérent")

        # 6) secret exposure marker not present
        marker_path = Path(os.getenv("SECRET_EXPOSURE_MARKER_PATH", "data/compromised_secret.marker"))
        checks["secret_exposure_marker"] = not marker_path.exists()
        if not checks["secret_exposure_marker"]:
            fail("secret_exposure_marker", f"Marker de compromission détecté: {marker_path}")

        # 7) leaked SSH key remediation acknowledged
        checks["leaked_ssh_ack"] = os.getenv("LEAKED_SSH_KEY_ROTATED_ACK", "false").lower() == "true"
        if not checks["leaked_ssh_ack"]:
            fail("leaked_ssh_ack", "LEAKED_SSH_KEY_ROTATED_ACK != true")

        # 8) known compromised fingerprint not configured
        fp = os.getenv("KRAKEN_API_KEY_FINGERPRINT", "").strip()
        checks["compromised_fingerprint"] = fp not in self.COMPROMISED_FINGERPRINTS
        if not checks["compromised_fingerprint"]:
            fail("compromised_fingerprint", f"Fingerprint compromis configuré: {fp}")

        # 8-bis) Shared-key multi-bot guardrail (recommended strategy A: one key per bot/host)
        allow_shared = os.getenv("ALLOW_SHARED_API_KEY", "false").lower() == "true"
        checks["shared_key_guard"] = True
        if stage in {"micro_live", "small_live"}:
            assignment_mode = os.getenv("API_KEY_ASSIGNMENT_MODE", "").strip().lower()
            unique_bot_id = os.getenv("UNIQUE_BOT_ID", "").strip()
            assigned_bot_id = os.getenv("API_KEY_ASSIGNED_BOT_ID", "").strip()
            if allow_shared:
                checks["shared_key_guard"] = False
                fail("shared_key_guard", "ALLOW_SHARED_API_KEY=true interdit en LIVE")
            if assignment_mode != "dedicated":
                checks["shared_key_guard"] = False
                fail("shared_key_guard", "API_KEY_ASSIGNMENT_MODE doit être 'dedicated' en LIVE")
            if not unique_bot_id or not assigned_bot_id or unique_bot_id != assigned_bot_id:
                checks["shared_key_guard"] = False
                fail("shared_key_guard", "UNIQUE_BOT_ID/API_KEY_ASSIGNED_BOT_ID invalides (clé non dédiée)")

        # Promotion ladder requirements
        checks["promotion_gate"] = self._check_promotion_gate(stage, paper_mode)
        if not checks["promotion_gate"]:
            fail("promotion_gate", f"Promotion gate failed for stage={stage}")

        # 9) Exchange connectivity + preflight checks
        if self.order_executor is None:
            fail("exchange_connectivity", "OrderExecutor absent")
            checks["exchange_connectivity"] = False
            checks["orders_endpoint"] = False
            checks["api_auth"] = False
            checks["nonce_health"] = False
            checks["db_writable"] = False
            checks["audit_writable"] = False
            checks["reconciliation_baseline"] = False
            checks["kill_switch_self_test"] = False
            checks["clock_drift"] = False
            return StartupAttestationResult(ok=False, checks=checks, reasons=reasons)

        checks["exchange_connectivity"] = await self._check_exchange_connectivity()
        if not checks["exchange_connectivity"]:
            fail("exchange_connectivity", "Exchange connectivity check failed")

        checks["api_auth"] = await self._check_api_auth()
        if not checks["api_auth"]:
            fail("api_auth", "API auth check failed")

        checks["orders_endpoint"] = await self._check_orders_endpoint()
        if not checks["orders_endpoint"]:
            fail("orders_endpoint", "Orders endpoint unreachable")

        checks["nonce_health"] = self._check_nonce_health()
        if not checks["nonce_health"]:
            fail("nonce_health", "Nonce generation unhealthy")

        checks["db_writable"] = self._check_db_writable()
        if not checks["db_writable"]:
            fail("db_writable", "Database not writable")

        checks["audit_writable"] = self._check_audit_writable()
        if not checks["audit_writable"]:
            fail("audit_writable", "Audit trail not writable")

        checks["clock_drift"] = await self._check_clock_drift()
        if not checks["clock_drift"]:
            fail("clock_drift", "Clock drift above allowed threshold")

        checks["reconciliation_baseline"] = await self._check_reconciliation_baseline()
        if not checks["reconciliation_baseline"]:
            fail("reconciliation_baseline", "Reconciliation baseline failed")

        checks["kill_switch_self_test"] = await self._kill_switch_self_test(preflight_only)
        if not checks["kill_switch_self_test"]:
            fail("kill_switch_self_test", "Kill switch self-test failed")

        ok = all(checks.values())
        return StartupAttestationResult(ok=ok, checks=checks, reasons=reasons)

    async def enforce(self, preflight_only: bool = False) -> None:
        result = await self.run(preflight_only=preflight_only)
        if not result.ok:
            for r in result.reasons:
                logger.error("Startup attestation FAILED: %s", r)
            raise StartupAttestationError("Startup attestation failed")
        logger.info("✅ Startup attestation passed")

    async def _check_exchange_connectivity(self) -> bool:
        try:
            ok, _resp = await self.order_executor._safe_api_call("Ticker", pair="XXBTZEUR")
            return bool(ok)
        except Exception:
            return False

    async def _check_api_auth(self) -> bool:
        try:
            balance = await self.order_executor.get_balance()
            return isinstance(balance, dict)
        except Exception:
            return False

    async def _check_orders_endpoint(self) -> bool:
        try:
            # balance + open orders path to ensure private endpoints are reachable
            _ = await self.order_executor.get_open_orders()
            return True
        except Exception:
            return False

    def _check_nonce_health(self) -> bool:
        try:
            n1 = self.order_executor._nonce_manager.next_nonce("startup_attest")
            n2 = self.order_executor._nonce_manager.next_nonce("startup_attest")
            return n2 > n1
        except Exception:
            return False

    def _check_db_writable(self) -> bool:
        try:
            from .persistence import get_persistence
            ps = get_persistence()
            with sqlite3.connect(str(ps.db_path)) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS startup_write_probe (
                        probe_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                probe_id = f"probe_{int(time.time()*1000)}"
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO startup_write_probe (probe_id, created_at) VALUES (?, ?)",
                    (probe_id, now),
                )
                conn.execute("DELETE FROM startup_write_probe WHERE probe_id = ?", (probe_id,))
                conn.commit()
            return True
        except Exception:
            return False

    def _check_audit_writable(self) -> bool:
        try:
            from .persistence import get_persistence
            ps = get_persistence()
            return ps.append_audit_event(
                event_id=f"startup_{int(time.time()*1000)}",
                event_type="STARTUP_PREFLIGHT",
                instance_id="system",
                config_hash="startup",
                risk_snapshot={"phase": "preflight"},
            )
        except Exception:
            return False

    async def _check_clock_drift(self) -> bool:
        max_drift_s = float(os.getenv("MAX_CLOCK_DRIFT_SECONDS", "5"))
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get("https://api.kraken.com/0/public/Time") as resp:
                    data = await resp.json()
                    exchange_unixtime = float(data.get("result", {}).get("unixtime", 0.0))
                    if exchange_unixtime <= 0:
                        return False
                    drift = abs(time.time() - exchange_unixtime)
                    return drift <= max_drift_s
        except Exception:
            return False

    async def _check_reconciliation_baseline(self) -> bool:
        try:
            local = float(os.getenv("INITIAL_CAPITAL", "0") or 0.0)
            balance = await self.order_executor.get_balance()
            exchange = float(balance.get("ZEUR", 0.0))
            divs = self.reconciler.compare_balances(local_total=local, exchange_total=exchange)
            return not self.reconciler.should_kill_switch(divs)
        except Exception:
            return False

    async def _kill_switch_self_test(self, preflight_only: bool) -> bool:
        if self.kill_switch is None:
            return False
        # Ensure object responds and is not already tripped at boot
        if self.kill_switch.tripped:
            return False
        if preflight_only:
            # light test path
            await self.kill_switch.check_partial_stuck(time.time(), max_partial_age_s=999999)
        return True

    def _check_global_kill_switch_clear(self) -> bool:
        if self.kill_switch is None:
            return False
        try:
            state = self.kill_switch.get_global_state()
            if state.tripped:
                return False
            if state.recovery_required:
                return False
            return True
        except Exception:
            return False

    def _check_promotion_gate(self, stage: str, paper_mode: bool) -> bool:
        """
        paper: paper mode mandatory
        micro_live: live confirmation + dedicated key + max instances <= 1
        small_live: micro_live requirements + explicit operator ack
        """
        if stage == "paper":
            return paper_mode
        max_instances = int(os.getenv("MAX_LIVE_INSTANCES", "1"))
        if stage == "micro_live":
            return (
                not paper_mode
                and os.getenv("LIVE_TRADING_CONFIRMATION", "false").lower() == "true"
                and os.getenv("API_KEY_ASSIGNMENT_MODE", "").strip().lower() == "dedicated"
                and max_instances <= 1
            )
        if stage == "small_live":
            return (
                not paper_mode
                and os.getenv("LIVE_TRADING_CONFIRMATION", "false").lower() == "true"
                and os.getenv("API_KEY_ASSIGNMENT_MODE", "").strip().lower() == "dedicated"
                and os.getenv("SMALL_LIVE_APPROVED", "false").lower() == "true"
                and max_instances <= 2
            )
        return False
