"""
DailyReporter — Résumé quotidien automatique du paper trading.

Génère à 00:00 UTC un résumé en langage humain de la journée de trading :
  "Aujourd'hui 12 trades. BTC/USD +1.8% PF 2.3, ETH/USD -0.4% PF 0.8..."

Stocke les rapports dans SQLite via le module persistence.
Thread-safe (RLock), O(1) par enregistrement de trade.

Usage:
    from autobot.v2.reports import DailyReporter

    reporter = DailyReporter(orchestrator)
    reporter.start()   # lance le scheduler interne
    reporter.stop()    # arrêt propre
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DailyReporter:
    """
    Génère un résumé quotidien de l'activité de trading.

    Collecte les trades de la journée, calcule les métriques clés et
    produit un rapport lisible stocké dans les logs et en base.

    Args:
        orchestrator: Référence à l'orchestrateur AutoBot.
        report_hour: Heure UTC du rapport (défaut 0 = minuit).
        report_minute: Minute UTC du rapport (défaut 0).
    """

    def __init__(
        self,
        orchestrator: Any,
        report_hour: int = 0,
        report_minute: int = 0,
        currency_symbol: str = "€",
    ) -> None:
        self._orchestrator = orchestrator
        self._report_hour = report_hour
        self._report_minute = report_minute
        self._currency = currency_symbol
        self._lock = threading.RLock()

        # Trades collectés pendant la journée courante
        self._daily_trades: List[Dict[str, Any]] = []
        self._daily_start: datetime = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Historique des rapports (dernier N)
        self._reports_history: List[Dict[str, Any]] = []
        self._max_history = 90  # 90 jours

        # Scheduler
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        logger.info(
            "DailyReporter initialisé — rapport quotidien à %02d:%02d UTC",
            report_hour, report_minute,
        )

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Démarre le scheduler de rapports quotidiens."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="DailyReporter"
        )
        self._thread.start()
        logger.info("DailyReporter démarré")

    def stop(self) -> None:
        """Arrête le scheduler proprement."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("DailyReporter arrêté")

    def record_trade(self, trade: Dict[str, Any]) -> None:
        """
        Enregistre un trade pour le rapport quotidien.

        Args:
            trade: Dictionnaire contenant au minimum:
                - pair: str (ex: "BTC/USD")
                - side: str ("buy" / "sell")
                - profit: float
                - volume: float
                - price: float
                - instance_id: str

        Thread-safe: Oui.
        Complexité: O(1).
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            # Reset si jour changé
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if today_start > self._daily_start:
                self._daily_trades.clear()
                self._daily_start = today_start

            trade_record = {
                "timestamp": now.isoformat(),
                "pair": trade.get("pair", "UNKNOWN"),
                "side": trade.get("side", "unknown"),
                "profit": trade.get("profit", 0.0),
                "volume": trade.get("volume", 0.0),
                "price": trade.get("price", 0.0),
                "instance_id": trade.get("instance_id", "unknown"),
            }
            self._daily_trades.append(trade_record)

    def generate_report(self, trades: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Génère le rapport pour les trades fournis (ou les trades du jour).

        Returns:
            Dictionnaire structuré du rapport.
        """
        with self._lock:
            if trades is None:
                trades = list(self._daily_trades)

        if not trades:
            return self._empty_report()

        # --- Métriques globales ---
        total_trades = len(trades)
        total_profit = sum(t.get("profit", 0.0) for t in trades)
        winners = [t for t in trades if t.get("profit", 0.0) > 0]
        losers = [t for t in trades if t.get("profit", 0.0) < 0]
        win_count = len(winners)
        loss_count = len(losers)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        # Profit Factor
        gross_profit = sum(t["profit"] for t in winners) if winners else 0.0
        gross_loss = abs(sum(t["profit"] for t in losers)) if losers else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        # --- Métriques par paire ---
        pairs_data: Dict[str, Dict] = defaultdict(lambda: {
            "trades": 0, "profit": 0.0, "wins": 0, "losses": 0
        })
        for t in trades:
            pair = t.get("pair", "UNKNOWN")
            pairs_data[pair]["trades"] += 1
            pairs_data[pair]["profit"] += t.get("profit", 0.0)
            if t.get("profit", 0.0) > 0:
                pairs_data[pair]["wins"] += 1
            elif t.get("profit", 0.0) < 0:
                pairs_data[pair]["losses"] += 1

        # Calcule PF par paire
        pairs_summary = {}
        for pair, data in pairs_data.items():
            p_wins = sum(t["profit"] for t in trades if t.get("pair") == pair and t.get("profit", 0) > 0)
            p_losses = abs(sum(t["profit"] for t in trades if t.get("pair") == pair and t.get("profit", 0) < 0))
            pf = (p_wins / p_losses) if p_losses > 0 else float("inf") if p_wins > 0 else 0.0
            pairs_summary[pair] = {
                "trades": data["trades"],
                "profit": round(data["profit"], 2),
                "win_rate": round(data["wins"] / data["trades"] * 100, 1) if data["trades"] > 0 else 0,
                "profit_factor": round(pf, 2) if pf != float("inf") else "∞",
            }

        # --- Texte humain ---
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [f"📊 Résumé du {date_str} — {total_trades} trade(s)"]
        lines.append(f"   P&L total: {total_profit:+.2f}{self._currency} | Win rate: {win_rate:.0f}% | PF: {profit_factor:.2f}")

        for pair, summary in sorted(pairs_summary.items()):
            pf_str = str(summary["profit_factor"])
            lines.append(f"   {pair}: {summary['profit']:+.2f}{self._currency} ({summary['trades']} trades, PF {pf_str})")

        if win_count > 0:
            best = max(trades, key=lambda t: t.get("profit", 0))
            lines.append(f"   🏆 Meilleur trade: {best.get('pair')} {best.get('profit', 0):+.2f}{self._currency}")
        if loss_count > 0:
            worst = min(trades, key=lambda t: t.get("profit", 0))
            lines.append(f"   💀 Pire trade: {worst.get('pair')} {worst.get('profit', 0):+.2f}{self._currency}")

        human_summary = "\n".join(lines)

        report = {
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_trades": total_trades,
            "total_profit": round(total_profit, 2),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "pairs": pairs_summary,
            "human_summary": human_summary,
        }

        return report

    def get_last_report(self) -> Optional[Dict[str, Any]]:
        """Retourne le dernier rapport généré."""
        with self._lock:
            return self._reports_history[-1] if self._reports_history else None

    def get_reports_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Retourne l'historique des rapports."""
        with self._lock:
            return list(self._reports_history[-days:])

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état du reporter."""
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "trades_today": len(self._daily_trades),
                "reports_count": len(self._reports_history),
                "last_report_date": self._reports_history[-1]["date"] if self._reports_history else None,
                "next_report_at": f"{self._report_hour:02d}:{self._report_minute:02d} UTC",
            }

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _empty_report(self) -> Dict[str, Any]:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_trades": 0,
            "total_profit": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "pairs": {},
            "human_summary": f"📊 Résumé du {date_str} — Aucun trade aujourd'hui.",
        }

    def _scheduler_loop(self) -> None:
        """Boucle de scheduler — attend 00:00 UTC pour générer le rapport."""
        logger.info("DailyReporter scheduler démarré")

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            # Calcule prochaine exécution
            target = now.replace(
                hour=self._report_hour,
                minute=self._report_minute,
                second=0, microsecond=0,
            )
            if now >= target:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.debug("DailyReporter: prochain rapport dans %.0f secondes", wait_seconds)

            # Attend (interruptible)
            if self._stop_event.wait(timeout=min(wait_seconds, 60)):
                break

            # Re-vérifie l'heure (on a pu attendre moins que wait_seconds)
            now = datetime.now(timezone.utc)
            if now.hour == self._report_hour and now.minute == self._report_minute:
                self._execute_daily_report()

    def _execute_daily_report(self) -> None:
        """Génère et stocke le rapport quotidien."""
        try:
            report = self.generate_report()

            # Log le résumé humain
            logger.info(report["human_summary"])

            # Stocke dans l'historique
            with self._lock:
                self._reports_history.append(report)
                if len(self._reports_history) > self._max_history:
                    self._reports_history = self._reports_history[-self._max_history:]

                # Reset trades pour le jour suivant
                self._daily_trades.clear()
                self._daily_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

            # Stocke en persistence si disponible
            try:
                from .persistence import get_persistence
                persistence = get_persistence()
                if hasattr(persistence, 'save_daily_report'):
                    persistence.save_daily_report(report)
            except Exception:
                pass  # Pas critique

            logger.info("DailyReporter: rapport du %s généré et stocké", report["date"])

        except Exception:
            logger.exception("DailyReporter: erreur génération rapport quotidien")


# ======================================================================
# Tests intégrés
# ======================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    passed = 0
    failed = 0

    def assert_test(name: str, condition: bool) -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")

    print("\n🧪 Tests DailyReporter")
    print("=" * 50)

    # Test 1: Création
    reporter = DailyReporter(orchestrator=None)
    assert_test("Création DailyReporter", reporter is not None)

    # Test 2: Record trade
    reporter.record_trade({
        "pair": "BTC/USD", "side": "sell", "profit": 25.50,
        "volume": 0.001, "price": 50000.0, "instance_id": "test-1"
    })
    reporter.record_trade({
        "pair": "BTC/USD", "side": "sell", "profit": -10.00,
        "volume": 0.001, "price": 49500.0, "instance_id": "test-1"
    })
    reporter.record_trade({
        "pair": "ETH/USD", "side": "sell", "profit": 15.00,
        "volume": 0.1, "price": 3000.0, "instance_id": "test-2"
    })
    reporter.record_trade({
        "pair": "ETH/USD", "side": "sell", "profit": 5.00,
        "volume": 0.05, "price": 3100.0, "instance_id": "test-2"
    })
    assert_test("Record 4 trades", len(reporter._daily_trades) == 4)

    # Test 3: Generate report
    report = reporter.generate_report()
    assert_test("Rapport généré", report is not None)
    assert_test("Total trades = 4", report["total_trades"] == 4)
    assert_test("Profit total = 35.50", abs(report["total_profit"] - 35.50) < 0.01)
    assert_test("Win count = 3", report["win_count"] == 3)
    assert_test("Loss count = 1", report["loss_count"] == 1)
    assert_test("Win rate = 75%", abs(report["win_rate"] - 75.0) < 0.1)

    # Test 4: Profit factor
    # Gross profit = 25.50 + 15.00 + 5.00 = 45.50
    # Gross loss = 10.00
    # PF = 4.55
    assert_test("Profit factor = 4.55", abs(report["profit_factor"] - 4.55) < 0.01)

    # Test 5: Pairs summary
    assert_test("2 paires dans le rapport", len(report["pairs"]) == 2)
    assert_test("BTC/USD dans le rapport", "BTC/USD" in report["pairs"])
    assert_test("ETH/USD dans le rapport", "ETH/USD" in report["pairs"])

    # Test 6: Human summary
    assert_test("Résumé humain non vide", len(report["human_summary"]) > 0)
    print(f"\n{report['human_summary']}")

    # Test 7: Empty report
    empty_reporter = DailyReporter(orchestrator=None)
    empty_report = empty_reporter.generate_report()
    assert_test("Rapport vide - 0 trades", empty_report["total_trades"] == 0)
    assert_test("Rapport vide - Aucun trade", "Aucun trade" in empty_report["human_summary"])

    # Test 8: Status
    status = reporter.get_status()
    assert_test("Status has trades_today", status["trades_today"] == 4)
    assert_test("Status has running", "running" in status)

    # Test 9: Thread safety
    import concurrent.futures
    thread_reporter = DailyReporter(orchestrator=None)

    def record_many(n: int) -> int:
        for i in range(n):
            thread_reporter.record_trade({
                "pair": "BTC/USD", "side": "sell", "profit": 1.0,
                "volume": 0.001, "price": 50000.0, "instance_id": f"t-{i}"
            })
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(record_many, 100) for _ in range(4)]
        results = [f.result() for f in futures]

    assert_test("Thread safety: 400 trades enregistrés", len(thread_reporter._daily_trades) == 400)

    # Test 10: Start/Stop scheduler
    reporter.start()
    assert_test("Scheduler démarré", reporter._thread is not None and reporter._thread.is_alive())
    reporter.stop()
    assert_test("Scheduler arrêté", not reporter._thread.is_alive())

    print(f"\n{'=' * 50}")
    print(f"Résultat: {passed}/{passed + failed} tests passés")
    sys.exit(0 if failed == 0 else 1)