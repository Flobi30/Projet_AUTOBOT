"""
main_async.py — Async entry point for AUTOBOT V2
MIGRATION P0: Replaces main.py (threading)

Uses:
- uvloop as event loop policy (if available)
- asyncio.run() for the main loop
- All components are async
"""

from __future__ import annotations

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

logger = logging.getLogger(__name__)


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
        logger.info("🔧 OS Tuning: %s", result.summary())
    except Exception as exc:
        logger.warning("⚠️ OS Tuning failed (non-fatal): %s", exc)


def _install_uvloop() -> bool:
    """Install uvloop as the default event loop policy."""
    try:
        import uvloop  # type: ignore[import-untyped]
        uvloop.install()
        logger.info("⚡ uvloop installé — event loop haute performance")
        return True
    except ImportError:
        logger.warning("⚠️ uvloop non disponible — utilisation de asyncio par défaut")
        logger.warning("   pip install uvloop  pour de meilleures performances")
        return False


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

    def _create_default_instance(self) -> InstanceConfig:
        return InstanceConfig(
            name="Instance Principale",
            symbol="XXBTZEUR",
            initial_capital=500.0,
            strategy="grid",
            leverage=1,
            grid_config={"range_percent": 7.0, "num_levels": 15},
        )

    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("🚀 DÉMARRAGE AUTOBOT V2 (ASYNC + uvloop)")
        logger.info("=" * 60)

        self.running = True

        try:
            # 1. Create orchestrator
            logger.info("🎛️ Initialisation OrchestratorAsync...")
            self.orchestrator = OrchestratorAsync(
                api_key=self.api_key, api_secret=self.api_secret
            )

            # 2. Create default instance
            config = self._create_default_instance()
            instance = await self.orchestrator.create_instance(config)
            if not instance:
                logger.error("❌ Impossible de créer l'instance par défaut")
                return

            # 3. Start orchestrator
            await self.orchestrator.start()
            
            # Démarrage du dashboard
            try:
                from autobot.v2.api.dashboard import DashboardServer
                self.dashboard = DashboardServer(host=None, port=self.dashboard_port)
                self.dashboard.start(self.orchestrator)
                logger.info(f"📊 Dashboard: http://{self.dashboard_host}:{self.dashboard_port}")
                logger.info(f"📈 API Health: http://{self.dashboard_host}:{self.dashboard_port}/health")
            except Exception as e:
                logger.warning(f"⚠️ Dashboard non démarré: {e}")

            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ AUTOBOT V2 ASYNC DÉMARRÉ!")
            logger.info("=" * 60)
            logger.info(f"   Instances: {len(self.orchestrator._instances)}")
            logger.info(f"   Max instances: {self.orchestrator.config['max_instances']}")
            logger.info("🛑 Arrêt: Ctrl+C")
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

        except Exception as exc:
            logger.exception(f"❌ Erreur fatale: {exc}")
            await self.stop()

    async def stop(self) -> None:
        if not self.running:
            return
        logger.info("🛑 Arrêt AUTOBOT V2 ASYNC...")
        self.running = False
        if self.orchestrator:
            await self.orchestrator.stop()
        logger.info("✅ Arrêt terminé")


def main() -> None:
    """Entry point."""
    # P5: Apply OS-level tuning before starting the event loop
    _apply_os_tuning()

    # Install uvloop
    _install_uvloop()

    # Check API keys
    if not os.getenv("KRAKEN_API_KEY") or not os.getenv("KRAKEN_API_SECRET"):
        logger.warning("⚠️ Clés API Kraken non définies — mode simulation")

    bot = AutoBotV2Async()
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
