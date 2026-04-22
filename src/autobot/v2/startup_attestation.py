from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
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
    status: str
    checks: Dict[str, bool]
    reasons: list[str]
    diagnostics: Dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "checks": self.checks,
            "reasons": self.reasons,
            "diagnostics": self.diagnostics,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass
class _CheckOutcome:
    ok: bool
    reason: str = "ok"
    message: str = "check passed"
    error_code: Optional[str] = None


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
        diagnostics: Dict[str, dict] = {}

        def record(name: str, outcome: _CheckOutcome | bool) -> None:
            if isinstance(outcome, bool):
                outcome = _CheckOutcome(
                    ok=outcome,
                    reason="ok" if outcome else f"{name}_failed",
                    message=f"{name} {'passed' if outcome else 'failed'}",
                )
            checks[name] = outcome.ok
            diagnostics[name] = {
                "status": "pass" if outcome.ok else "fail",
                "reason": outcome.reason,
                "message": outcome.message,
                "error_code": outcome.error_code,
            }
            if not outcome.ok:
                reasons.append(outcome.reason)

        def pass_check(name: str, message: str = "check passed") -> None:
            record(name, _CheckOutcome(ok=True, reason="ok", message=message))

        def fail(name: str, reason: str, message: str, error_code: Optional[str] = None) -> None:
            record(name, _CheckOutcome(ok=False, reason=reason, message=message, error_code=error_code))

        # 1) APP_ENV validity
        if self.app_env in self.VALID_ENVS:
            pass_check("app_env_valid", "APP_ENV accepted")
        else:
            fail("app_env_valid", "invalid_app_env", f"APP_ENV invalide: {self.app_env}")

        paper_mode = os.getenv("PAPER_TRADING", "false").lower() == "true"
        stage = os.getenv("DEPLOYMENT_STAGE", "paper").strip().lower()
        if stage in self.VALID_STAGES:
            pass_check("deployment_stage_valid", "DEPLOYMENT_STAGE accepted")
        else:
            fail("deployment_stage_valid", "invalid_deployment_stage", f"DEPLOYMENT_STAGE invalide: {stage}")
        # 2) live confirmation gate
        if paper_mode or os.getenv("LIVE_TRADING_CONFIRMATION", "false").lower() == "true":
            pass_check("live_confirmation", "live confirmation gate satisfied")
        else:
            fail("live_confirmation", "live_confirmation_missing", "LIVE mode sans LIVE_TRADING_CONFIRMATION=true")

        # 3) auth token present
        if bool(os.getenv("DASHBOARD_API_TOKEN", "").strip()):
            pass_check("dashboard_token", "dashboard token detected")
        else:
            fail("dashboard_token", "dashboard_token_missing", "DASHBOARD_API_TOKEN manquant", error_code="auth")

        # 4) required risk limits present
        risk_required = ["MAX_DRAWDOWN_PCT", "RISK_PER_TRADE_PCT", "MAX_POSITION_SIZE_PCT"]
        if all(os.getenv(k) not in (None, "") for k in risk_required):
            pass_check("risk_limits", "risk limits configured")
        else:
            fail(
                "risk_limits",
                "risk_limits_missing",
                f"Risk limits manquants: {[k for k in risk_required if os.getenv(k) in (None, '')]}",
            )

        # 5) kill switch initialized
        if self.kill_switch is not None:
            pass_check("kill_switch_initialized", "kill switch initialized")
        else:
            fail("kill_switch_initialized", "kill_switch_not_initialized", "Kill switch non initialisé")

        # 6) secret exposure marker not present
        marker_path = Path(os.getenv("SECRET_EXPOSURE_MARKER_PATH", "data/compromised_secret.marker"))
        if not marker_path.exists():
            pass_check("secret_exposure_marker", "no secret exposure marker")
        else:
            fail("secret_exposure_marker", "secret_exposure_marker_found", f"Marker de compromission détecté: {marker_path}")

        # 7) leaked SSH key remediation acknowledged
        if os.getenv("LEAKED_SSH_KEY_ROTATED_ACK", "false").lower() == "true":
            pass_check("leaked_ssh_ack", "leaked ssh key remediation acknowledged")
        else:
            fail("leaked_ssh_ack", "leaked_ssh_ack_missing", "LEAKED_SSH_KEY_ROTATED_ACK != true")

        # 8) known compromised fingerprint not configured
        fp = os.getenv("KRAKEN_API_KEY_FINGERPRINT", "").strip()
        if fp not in self.COMPROMISED_FINGERPRINTS:
            pass_check("compromised_fingerprint", "no known compromised fingerprint")
        else:
            fail("compromised_fingerprint", "compromised_fingerprint_configured", f"Fingerprint compromis configuré: {fp}")

        # 8-bis) Shared-key multi-bot guardrail (recommended strategy A: one key per bot/host)
        allow_shared = os.getenv("ALLOW_SHARED_API_KEY", "false").lower() == "true"
        pass_check("shared_key_guard", "shared key guard passed")
        if stage in {"micro_live", "small_live"}:
            assignment_mode = os.getenv("API_KEY_ASSIGNMENT_MODE", "").strip().lower()
            unique_bot_id = os.getenv("UNIQUE_BOT_ID", "").strip()
            assigned_bot_id = os.getenv("API_KEY_ASSIGNED_BOT_ID", "").strip()
            if allow_shared:
                fail("shared_key_guard", "shared_api_key_forbidden", "ALLOW_SHARED_API_KEY=true interdit en LIVE")
            if assignment_mode != "dedicated":
                fail("shared_key_guard", "api_key_assignment_not_dedicated", "API_KEY_ASSIGNMENT_MODE doit être 'dedicated' en LIVE")
            if not unique_bot_id or not assigned_bot_id or unique_bot_id != assigned_bot_id:
                fail("shared_key_guard", "api_key_bot_id_mismatch", "UNIQUE_BOT_ID/API_KEY_ASSIGNED_BOT_ID invalides (clé non dédiée)")

        # Promotion ladder requirements
        if self._check_promotion_gate(stage, paper_mode):
            pass_check("promotion_gate", "promotion gate passed")
        else:
            fail("promotion_gate", "promotion_gate_failed", f"Promotion gate failed for stage={stage}")

        # 9) Exchange connectivity + preflight checks
        if self.order_executor is None:
            fail("exchange_connectivity", "order_executor_missing", "OrderExecutor absent")
            fail("orders_endpoint", "order_executor_missing", "OrderExecutor absent")
            fail("api_auth", "order_executor_missing", "OrderExecutor absent")
            fail("nonce_health", "order_executor_missing", "OrderExecutor absent")
            fail("db_writable", "order_executor_missing", "OrderExecutor absent")
            fail("audit_writable", "order_executor_missing", "OrderExecutor absent")
            fail("reconciliation_baseline", "order_executor_missing", "OrderExecutor absent")
            fail("kill_switch_self_test", "order_executor_missing", "OrderExecutor absent")
            fail("clock_drift", "order_executor_missing", "OrderExecutor absent")
            return StartupAttestationResult(
                ok=False,
                status="fail",
                checks=checks,
                reasons=reasons,
                diagnostics=diagnostics,
            )

        record("exchange_connectivity", await self._check_exchange_connectivity())
        record("api_auth", await self._check_api_auth())
        record("orders_endpoint", await self._check_orders_endpoint())
        record("nonce_health", self._check_nonce_health())
        record("db_writable", self._check_db_writable())
        record("audit_writable", self._check_audit_writable())
        record("clock_drift", await self._check_clock_drift())
        record("reconciliation_baseline", await self._check_reconciliation_baseline())
        record("kill_switch_self_test", await self._kill_switch_self_test(preflight_only))

        ok = all(checks.values())
        return StartupAttestationResult(
            ok=ok,
            status="pass" if ok else "fail",
            checks=checks,
            reasons=reasons,
            diagnostics=diagnostics,
        )

    async def enforce(self, preflight_only: bool = False) -> None:
        result = await self.run(preflight_only=preflight_only)
        if not result.ok:
            for r in result.reasons:
                logger.error("Startup attestation FAILED: %s", r)
            raise StartupAttestationError("Startup attestation failed")
        logger.info("✅ Startup attestation passed")

    def _log_check_exception(self, check_name: str, error_code: str, exc: Exception) -> None:
        logger.error(
            "startup_attestation_check_failed",
            extra={
                "check": check_name,
                "error_code": error_code,
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )

    async def _check_exchange_connectivity(self) -> _CheckOutcome:
        try:
            ok, _resp = await self.order_executor._safe_api_call("Ticker", pair="XXBTZEUR")
            if bool(ok):
                return _CheckOutcome(ok=True, message="exchange ticker call succeeded")
            return _CheckOutcome(ok=False, reason="exchange_connectivity_failed", message="Ticker endpoint returned not-ok", error_code="network")
        except asyncio.TimeoutError as exc:
            self._log_check_exception("exchange_connectivity", "timeout", exc)
            return _CheckOutcome(ok=False, reason="exchange_connectivity_timeout", message="Exchange ticker timed out", error_code="timeout")
        except aiohttp.ClientError as exc:
            self._log_check_exception("exchange_connectivity", "network", exc)
            return _CheckOutcome(ok=False, reason="exchange_connectivity_network_error", message="Exchange connectivity client error", error_code="network")

    async def _check_api_auth(self) -> _CheckOutcome:
        try:
            balance = await self.order_executor.get_balance()
            if isinstance(balance, dict):
                return _CheckOutcome(ok=True, message="balance auth call succeeded")
            return _CheckOutcome(ok=False, reason="api_auth_invalid_payload", message="Balance payload is not a dict", error_code="auth")
        except PermissionError as exc:
            self._log_check_exception("api_auth", "auth", exc)
            return _CheckOutcome(ok=False, reason="api_auth_permission_denied", message="API auth permission denied", error_code="auth")
        except ValueError as exc:
            self._log_check_exception("api_auth", "auth", exc)
            return _CheckOutcome(ok=False, reason="api_auth_invalid_response", message="API auth returned malformed data", error_code="auth")
        except asyncio.TimeoutError as exc:
            self._log_check_exception("api_auth", "timeout", exc)
            return _CheckOutcome(ok=False, reason="api_auth_timeout", message="API auth request timed out", error_code="timeout")
        except aiohttp.ClientError as exc:
            self._log_check_exception("api_auth", "network", exc)
            return _CheckOutcome(ok=False, reason="api_auth_network_error", message="API auth network error", error_code="network")

    async def _check_orders_endpoint(self) -> _CheckOutcome:
        try:
            # balance + open orders path to ensure private endpoints are reachable
            _ = await self.order_executor.get_open_orders()
            return _CheckOutcome(ok=True, message="orders endpoint reachable")
        except PermissionError as exc:
            self._log_check_exception("orders_endpoint", "auth", exc)
            return _CheckOutcome(ok=False, reason="orders_endpoint_auth_error", message="Orders endpoint auth error", error_code="auth")
        except asyncio.TimeoutError as exc:
            self._log_check_exception("orders_endpoint", "timeout", exc)
            return _CheckOutcome(ok=False, reason="orders_endpoint_timeout", message="Orders endpoint timeout", error_code="timeout")
        except aiohttp.ClientError as exc:
            self._log_check_exception("orders_endpoint", "network", exc)
            return _CheckOutcome(ok=False, reason="orders_endpoint_network_error", message="Orders endpoint unreachable", error_code="network")

    def _check_nonce_health(self) -> _CheckOutcome:
        try:
            n1 = self.order_executor._nonce_manager.next_nonce("startup_attest")
            n2 = self.order_executor._nonce_manager.next_nonce("startup_attest")
            if n2 > n1:
                return _CheckOutcome(ok=True, message="nonce progression healthy")
            return _CheckOutcome(ok=False, reason="nonce_not_increasing", message="Nonce did not increase")
        except OSError as exc:
            self._log_check_exception("nonce_health", "io", exc)
            return _CheckOutcome(ok=False, reason="nonce_io_error", message="Nonce store I/O error", error_code="io")
        except AttributeError as exc:
            self._log_check_exception("nonce_health", "io", exc)
            return _CheckOutcome(ok=False, reason="nonce_manager_missing", message="Nonce manager missing", error_code="io")

    def _check_db_writable(self) -> _CheckOutcome:
        health_db_path = os.getenv("STARTUP_HEALTH_DB_PATH", "").strip()
        try:
            from .persistence import get_persistence

            db_path = Path(health_db_path) if health_db_path else Path(get_persistence().db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            token = f"startup_attest_{time.time_ns()}"
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS startup_health_checks (
                        check_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
                conn.execute("INSERT INTO startup_health_checks (check_id) VALUES (?)", (token,))
                row = conn.execute(
                    "SELECT check_id FROM startup_health_checks WHERE check_id = ?",
                    (token,),
                ).fetchone()
                conn.execute("DELETE FROM startup_health_checks WHERE check_id = ?", (token,))
                conn.commit()

            if row and row[0] == token:
                return _CheckOutcome(ok=True, message=f"database read/write probe succeeded ({db_path})")
            return _CheckOutcome(
                ok=False,
                reason="db_readback_failed",
                message="Database readback probe failed",
                error_code="io",
            )
        except PermissionError as exc:
            self._log_check_exception("db_writable", "io", exc)
            return _CheckOutcome(
                ok=False,
                reason="db_write_permission_denied",
                message="Database write permission denied",
                error_code="io",
            )
        except asyncio.TimeoutError as exc:
            self._log_check_exception("db_writable", "timeout", exc)
            return _CheckOutcome(
                ok=False,
                reason="db_io_timeout",
                message="Database I/O timed out",
                error_code="timeout",
            )
        except sqlite3.OperationalError as exc:
            err = str(exc).lower()
            if "database is locked" in err or "busy" in err:
                self._log_check_exception("db_writable", "timeout", exc)
                return _CheckOutcome(
                    ok=False,
                    reason="db_io_timeout",
                    message="Database busy/locked timeout during read-write probe",
                    error_code="timeout",
                )
            if "disk is full" in err or "database or disk is full" in err:
                self._log_check_exception("db_writable", "io", exc)
                return _CheckOutcome(
                    ok=False,
                    reason="db_disk_full",
                    message="Database disk is full",
                    error_code="io",
                )
            self._log_check_exception("db_writable", "io", exc)
            return _CheckOutcome(ok=False, reason="db_io_error", message="Database read-write probe failed", error_code="io")
        except OSError as exc:
            self._log_check_exception("db_writable", "io", exc)
            if exc.errno == errno.ENOSPC:
                return _CheckOutcome(ok=False, reason="db_disk_full", message="Database disk is full", error_code="io")
            if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
                return _CheckOutcome(
                    ok=False,
                    reason="db_write_permission_denied",
                    message="Database write permission denied",
                    error_code="io",
                )
            if exc.errno in (errno.ETIMEDOUT,):
                return _CheckOutcome(ok=False, reason="db_io_timeout", message="Database I/O timed out", error_code="timeout")
            return _CheckOutcome(ok=False, reason="db_io_error", message="Database read-write probe failed", error_code="io")

    def _check_audit_writable(self) -> _CheckOutcome:
        try:
            from .persistence import get_persistence
            ps = get_persistence()
            ok = ps.append_audit_event(
                event_id=f"startup_{int(time.time()*1000)}",
                event_type="STARTUP_PREFLIGHT",
                instance_id="system",
                config_hash="startup",
                risk_snapshot={"phase": "preflight"},
            )
            if ok:
                return _CheckOutcome(ok=True, message="audit trail writable")
            return _CheckOutcome(ok=False, reason="audit_write_failed", message="Audit trail not writable", error_code="io")
        except OSError as exc:
            self._log_check_exception("audit_writable", "io", exc)
            return _CheckOutcome(ok=False, reason="audit_io_error", message="Audit trail I/O error", error_code="io")

    async def _check_clock_drift(self) -> _CheckOutcome:
        max_drift_s = float(os.getenv("MAX_CLOCK_DRIFT_SECONDS", "5"))
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get("https://api.kraken.com/0/public/Time") as resp:
                    data = await resp.json()
                    exchange_unixtime = float(data.get("result", {}).get("unixtime", 0.0))
                    if exchange_unixtime <= 0:
                        return _CheckOutcome(ok=False, reason="clock_drift_invalid_exchange_time", message="Exchange time invalid", error_code="network")
                    drift = abs(time.time() - exchange_unixtime)
                    if drift <= max_drift_s:
                        return _CheckOutcome(ok=True, message="clock drift in tolerance")
                    return _CheckOutcome(ok=False, reason="clock_drift_exceeded", message="Clock drift above allowed threshold")
        except asyncio.TimeoutError as exc:
            self._log_check_exception("clock_drift", "timeout", exc)
            return _CheckOutcome(ok=False, reason="clock_drift_timeout", message="Clock drift check timed out", error_code="timeout")
        except aiohttp.ClientError as exc:
            self._log_check_exception("clock_drift", "network", exc)
            return _CheckOutcome(ok=False, reason="clock_drift_network_error", message="Clock drift network error", error_code="network")

    async def _check_reconciliation_baseline(self) -> _CheckOutcome:
        try:
            local = float(os.getenv("INITIAL_CAPITAL", "0") or 0.0)
            balance = await self.order_executor.get_balance()
            exchange = float(balance.get("ZEUR", 0.0))
            divs = self.reconciler.compare_balances(local_total=local, exchange_total=exchange)
            if not self.reconciler.should_kill_switch(divs):
                return _CheckOutcome(ok=True, message="reconciliation baseline accepted")
            return _CheckOutcome(ok=False, reason="reconciliation_divergence", message="Reconciliation baseline failed")
        except ValueError as exc:
            self._log_check_exception("reconciliation_baseline", "io", exc)
            return _CheckOutcome(ok=False, reason="reconciliation_invalid_balance", message="Invalid reconciliation balance payload", error_code="io")
        except asyncio.TimeoutError as exc:
            self._log_check_exception("reconciliation_baseline", "timeout", exc)
            return _CheckOutcome(ok=False, reason="reconciliation_timeout", message="Reconciliation request timed out", error_code="timeout")
        except aiohttp.ClientError as exc:
            self._log_check_exception("reconciliation_baseline", "network", exc)
            return _CheckOutcome(ok=False, reason="reconciliation_network_error", message="Reconciliation network failure", error_code="network")

    async def _kill_switch_self_test(self, preflight_only: bool) -> _CheckOutcome:
        if self.kill_switch is None:
            return _CheckOutcome(ok=False, reason="kill_switch_not_initialized", message="Kill switch not initialized")
        # Ensure object responds and is not already tripped at boot
        if self.kill_switch.tripped:
            return _CheckOutcome(ok=False, reason="kill_switch_already_tripped", message="Kill switch already tripped")
        if preflight_only:
            # light test path
            await self.kill_switch.check_partial_stuck(time.time(), max_partial_age_s=999999)
        return _CheckOutcome(ok=True, message="kill switch self-test passed")

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
