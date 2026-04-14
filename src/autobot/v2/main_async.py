"""
main_async.py — Async entry point for AUTOBOT V2
MIGRATION P0: Replaces main.py (threading)

V3: Adaptive Grid support
- Uses PairProfileRegistry for per-pair config
- Passes pair profile to grid strategy via grid_config
- Multi-grid support (short-term + long-term) for eligible pairs

Uses:
- uvloop as event loop policy (if available)
- asyncio.run() for the main loop
- All components are async
"""

from __future__ import annotations

# ── Load .env file BEFORE any module reads env vars ──────────────
# This ensures MODULE_* variables from .env are available to os.getenv()
from dotenv import load_dotenv as _load_dotenv
from pathlib import Path as _DotenvPath

# Try multiple locations: /app/.env (Docker), or project root .env
for _env_candidate in [
    _DotenvPath("/app/.env"),
    _DotenvPath(__file__).resolve().parent.parent.parent.parent / ".env",
]:
    if _env_candidate.is_file():
        _load_dotenv(_env_candidate, override=False)
        break

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

# SEC-04: validate path before inserting into sys.path
_src_path = Path(__file__).parent.parent.parent.resolve()
if _src_path.exists() and _src_path.is_dir():
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))

# Setup logging  # noqa: E402
from autobot.v2.utils import setup_structured_logging  # noqa: E402

setup_structured_logging(
    level=logging.INFO,
    log_file="autobot_async.log",
    max_bytes=10 * 1024 * 1024,
    backup_count=5,
    use_json=True,
)

from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.orchestrator import InstanceConfig
from autobot.v2.os_tuning import OSTuner
from autobot.v2.api.dashboard import DashboardServer
from autobot.v2.order_executor_async import OrderExecutorAsync
from autobot.v2.kill_switch import KillSwitch
from autobot.v2.startup_attestation import StartupAttestation, StartupAttestationError

logger = logging.getLogger(__name__)


# V3: Import adaptive grid config (optional — graceful degradation)


def _parse_float_env(name: str, default: float, min_val: float, max_val: float) -> float:
    try:
        val = float(os.getenv(name, str(default)))
        return max(min_val, min(max_val, val))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name}, using default {default}")
        return default

def _parse_int_env(name: str, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(os.getenv(name, str(default)))
        return max(min_val, min(max_val, val))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name}, using default {default}")
        return default
_pair_registry = None
try:
    from autobot.v2.strategies.adaptive_grid_config import get_default_registry
    _pair_registry = get_default_registry()
    logger.info("V3 Adaptive Grid: PairProfileRegistry loaded (%d profiles)", len(_pair_registry.symbols))
except ImportError:
    logger.warning("V3 Adaptive Grid not available — using legacy fixed config")


# ------------------------------------------------------------------
# Install uvloop (if available)
# ------------------------------------------------------------------

def _apply_os_tuning(
    cpu_cores: set[int] | None = None,
    enable_rt: bool = False,
) -> None:
    """Apply startup-time OS-level optimisations (P5)."""
    try:
        tuner = OSTuner()
        result = tuner.apply_all(cpu_cores=cpu_cores, enable_rt_scheduling=enable_rt)
        logger.info("OS Tuning: %s", result.summary())
    except Exception as exc:
        logger.warning("OS Tuning failed (non-fatal): %s", exc)


def _install_uvloop() -> bool:
    """Install uvloop as the default event loop policy."""
    try:
        import uvloop  # type: ignore[import-untyped]
        uvloop.install()
        logger.info("uvloop installe — event loop haute performance")
        return True
    except ImportError:
        logger.warning("uvloop non disponible — utilisation de asyncio par defaut")
        logger.warning("   pip install uvloop  pour de meilleures performances")
        return False


def _build_grid_config(symbol: str) -> dict:
    """Build grid_config for a given symbol using V3 registry or legacy defaults.

    V3: If a PairProfile exists, injects it into grid_config so that
    GridStrategyAsync can switch to adaptive mode.

    Legacy fallback: returns {"range_percent": 2.0, "num_levels": 20}.
    """
    if _pair_registry is not None and _pair_registry.has(symbol):
        profile = _pair_registry.get(symbol)
        return {
            "range_percent": profile.base_range_pct,
            "num_levels": profile.base_num_levels,
            "max_capital_per_level": profile.max_capital_per_level,
            "pair_profile": profile,
            # SmartRecentering V3 defaults (can be overridden via env)
            "dgt_drift_threshold_pct": _parse_float_env("DGT_DRIFT_PCT", 5.0, 1.0, 20.0),
            "dgt_cooldown_minutes": _parse_int_env("DGT_COOLDOWN_MIN", 45, 5, 1440),
            "dgt_max_recenters_per_day": _parse_int_env("DGT_MAX_RECENTERS", 4, 1, 100),
        }
    else:
        # Legacy: 7% range, 15 levels (unchanged from V2)
        return {"range_percent": 2.0, "num_levels": 20}


class AutoBotV2Async:
    """Async application for AUTOBOT V2."""

    def __init__(
        self,
        dashboard_host: str = "127.0.0.1",
        dashboard_port: int = 8080,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self.orchestrator: Optional[OrchestratorAsync] = None
        self.dashboard = None
        self.running = False
        self.dashboard_host = dashboard_host
        self.dashboard_port = dashboard_port
        self.api_key = api_key or os.getenv("KRAKEN_API_KEY")
        self.api_secret = api_secret or os.getenv("KRAKEN_API_SECRET")
        self.startup_kill_switch = KillSwitch()

    def _create_all_instance_configs(self) -> list:
        """Create instance configs for all TRADING_PAIRS (multi-pair support).
        
        Reads TRADING_PAIRS env var (comma-separated Kraken symbols).
        Falls back to TRADING_SYMBOL for backward compatibility.
        Capital is split equally across all pairs.
        """
        pairs_str = os.getenv("TRADING_PAIRS", "")
        if pairs_str:
            symbols = [s.strip() for s in pairs_str.split(",") if s.strip()]
        else:
            symbols = [os.getenv("TRADING_SYMBOL", "XXBTZEUR")]
        
        total_capital = float(os.getenv("INITIAL_CAPITAL", 1000.0))
        capital_per_pair = total_capital / len(symbols)
        
        # Capital weighting: BTC and ETH get more (1.5x), alts get standard (1.0x)
        weights = {}
        for s in symbols:
            if "XBT" in s or "BTC" in s:
                weights[s] = 1.5
            elif "ETH" in s:
                weights[s] = 1.3
            else:
                weights[s] = 1.0
        total_weight = sum(weights.values())
        
        configs = []
        for symbol in symbols:
            weighted_capital = total_capital * (weights[symbol] / total_weight)
            grid_config = _build_grid_config(symbol)
            
            # Friendly name mapping
            name_map = {
                "XXBTZEUR": "BTC/EUR", "XETHZEUR": "ETH/EUR",
                "SOLEUR": "SOL/EUR", "ADAEUR": "ADA/EUR",
                "DOTEUR": "DOT/EUR", "XXRPZEUR": "XRP/EUR",
                "LINKEUR": "LINK/EUR", "POLEUR": "POL/EUR",
                "AVAXEUR": "AVAX/EUR", "UNIEUR": "UNI/EUR",
            }
            name = name_map.get(symbol, symbol)
            
            configs.append(InstanceConfig(
                name=f"Grid {name}",
                symbol=symbol,
                initial_capital=round(weighted_capital, 2),
                strategy="grid",
                leverage=1,
                grid_config=grid_config,
            ))
        
        logger.info(f"Multi-pair: {len(configs)} pairs, total capital={total_capital}")
        for cfg in configs:
            logger.info(f"  {cfg.symbol}: {cfg.initial_capital:.2f} EUR")
        
        return configs

    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("DEMARRAGE AUTOBOT V2 (ASYNC + uvloop + Adaptive Grid V3)")
        logger.info("=" * 60)

        self.running = True

        try:
            # 0. Startup attestation hard-block gate
            preflight_only = os.getenv("PREFLIGHT_ONLY", "false").lower() == "true"
            attestation_executor = OrderExecutorAsync(self.api_key, self.api_secret)
            try:
                attestation = StartupAttestation(
                    order_executor=attestation_executor,
                    kill_switch=self.startup_kill_switch,
                )
                await attestation.enforce(preflight_only=preflight_only)
                if preflight_only:
                    logger.info("✅ PREFLIGHT_ONLY=true: checks passed, trading not started.")
                    self.running = False
                    return
            finally:
                await attestation_executor.close()

            # 1. Create orchestrator
            logger.info("Initialisation OrchestratorAsync...")
            self.orchestrator = OrchestratorAsync(
                api_key=self.api_key, api_secret=self.api_secret
            )

            # 2. Create instances for all configured trading pairs
            configs = self._create_all_instance_configs()
            instances_created = 0
            for config in configs:
                instance = await self.orchestrator.create_instance(config)
                if instance:
                    instances_created += 1
                    logger.info(f"  Created: {config.name} ({config.symbol})")
                else:
                    logger.warning(f"  Failed: {config.name} ({config.symbol})")
            
            if instances_created == 0:
                logger.error("Impossible de creer aucune instance")
                return
            
            logger.info(f"Created {instances_created}/{len(configs)} instances")

            # 3. Start orchestrator
            await self.orchestrator.start()
            
            # Dashboard
            try:
                from autobot.v2.api.dashboard import DashboardServer
                self.dashboard = DashboardServer(host=None, port=self.dashboard_port)
                self.dashboard.start(self.orchestrator)
                logger.info(f"Dashboard: http://{self.dashboard_host}:{self.dashboard_port}")
                logger.info(f"API Health: http://{self.dashboard_host}:{self.dashboard_port}/health")
            except Exception as e:
                logger.warning(f"Dashboard non demarre: {e}")

            logger.info("")
            logger.info("=" * 60)
            logger.info("AUTOBOT V2 ASYNC DEMARRE!")
            logger.info("=" * 60)
            logger.info(f"   Instances: {len(self.orchestrator._instances)}")
            logger.info(f"   Max instances: {self.orchestrator.config['max_instances']}")

            # V3: Log adaptive grid status for all pairs
            if _pair_registry:
                logger.info(f"   Adaptive Grid V3: {len(_pair_registry.symbols)} pair profiles loaded")
                for cfg in configs:
                    if _pair_registry.has(cfg.symbol):
                        profile = _pair_registry.get(cfg.symbol)
                        logger.info(
                            f"   {cfg.symbol}: range={profile.base_range_pct}%% "
                            f"[{profile.min_range_pct}-{profile.max_range_pct}%%], "
                            f"levels={profile.base_num_levels} [{profile.min_levels}-{profile.max_levels}]"
                        )

            # Log module manager status
            if self.orchestrator.module_manager:
                mm_status = self.orchestrator.module_manager.get_status()
                logger.info(f"   Modules: {mm_status['total_loaded']}/{mm_status['total_enabled']} loaded")
                if self.orchestrator.module_manager.loaded_modules:
                    logger.info(f"   Active: {', '.join(self.orchestrator.module_manager.loaded_modules)}")

            logger.info("Arret: Ctrl+C")
            logger.info("")

            # 4. Setup signal handlers
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

            # 5. Keep running with health reporting (PROD-01)
            _health_tick = 0
            while self.running:
                await asyncio.sleep(1)
                _health_tick += 1
                if _health_tick % 60 == 0:
                    status = self.orchestrator.get_status()
                    logger.info(
                        "Health: running=%s instances=%d ws=%s",
                        status['running'],
                        status['instance_count'],
                        status['websocket_connected'],
                    )

        except StartupAttestationError as exc:
            logger.error(f"Startup blocked by attestation gate: {exc}")
            self.running = False
        except Exception as exc:
            logger.exception(f"Erreur fatale: {exc}")
            await self.stop()

    async def stop(self) -> None:
        if not self.running:
            return
        logger.info("Arret AUTOBOT V2 ASYNC...")
        self.running = False
        if self.orchestrator:
            await self.orchestrator.stop()
        logger.info("Arret termine")


def main() -> None:
    """Entry point."""
    # P5: Apply OS-level tuning before starting the event loop
    _apply_os_tuning()

    # Install uvloop
    _install_uvloop()

    # Check API keys
    if not os.getenv("KRAKEN_API_KEY") or not os.getenv("KRAKEN_API_SECRET"):
        logger.warning("Cles API Kraken non definies — mode simulation")

    bot = AutoBotV2Async()
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
