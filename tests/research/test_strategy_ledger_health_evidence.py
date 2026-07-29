import ast
import json
import sqlite3
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.research.strategy_ledger_health_evidence import (
    StrategyLedgerHealthEvidenceConfig,
    build_strategy_ledger_health_evidence,
)


pytestmark = pytest.mark.unit


def _create_state_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                position_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                expected_price REAL,
                executed_price REAL NOT NULL,
                volume REAL NOT NULL,
                fees REAL DEFAULT 0,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER DEFAULT 0,
                is_closing_leg INTEGER DEFAULT 0,
                decision_id TEXT,
                signal_id TEXT,
                strategy_id TEXT,
                timeframe TEXT,
                signal_source TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                regime TEXT,
                execution_mode TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _insert_closed_pair(
    path: Path,
    *,
    position_id: str,
    execution_mode: str,
    net_pnl: float,
    strategy_id: str = "trend_momentum",
) -> None:
    with sqlite3.connect(path) as conn:
        rows = [
            (
                f"{position_id}-open", position_id, "pytest", "BTCEUR", "buy", 100.0, 100.0, 1.0,
                0.1, 1.0, None, 1, 0, None, None, strategy_id, "5m", "pytest", None, None,
                "trend", execution_mode, "2026-07-29T00:00:00+00:00",
            ),
            (
                f"{position_id}-close", position_id, "pytest", "BTCEUR", "sell", 100.0, 100.0, 1.0,
                0.1, 1.0, net_pnl, 0, 1, None, None, strategy_id, "5m", "pytest", net_pnl + 0.2, net_pnl,
                "trend", execution_mode, "2026-07-29T01:00:00+00:00",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price, volume,
             fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg, decision_id, signal_id,
             strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime, execution_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "decision_statuses": ["learning", "shadow_passed", "rejected", "retired_from_execution"],
                "live_auto_promotion_allowed": False,
                "hypotheses": [
                    {
                        "strategy_id": "trend_momentum",
                        "family": "trend",
                        "hypothesis": "pytest",
                        "market": "spot_crypto",
                        "timeframe": "5m",
                        "required_data": ["ohlcv"],
                        "entry_logic": "pytest",
                        "exit_logic": "pytest",
                        "risk_model": "pytest",
                        "fees_model": {"profile": "paper_current_taker"},
                        "slippage_model": {"profile": "paper_current_taker"},
                        "expected_market_regime": "trend",
                        "failure_modes": ["insufficient_edge"],
                        "baseline_comparison": {"no_trade": "required"},
                        "validation_status": "shadow_passed",
                        "paper_status": "shadow_only",
                        "decision": "continue_testing",
                        "decision_reason": "pytest",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_health_evidence_reads_only_shadow_metrics_and_ignores_paper_capital(tmp_path: Path) -> None:
    state_db = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(state_db)
    _write_registry(registry)
    _insert_closed_pair(state_db, position_id="shadow-loss", execution_mode="shadow_paper", net_pnl=-1.0)
    _insert_closed_pair(state_db, position_id="paper-win", execution_mode="paper_capital", net_pnl=99.0)
    before = state_db.read_bytes()

    evidence = build_strategy_ledger_health_evidence(
        StrategyLedgerHealthEvidenceConfig(
            state_db_path=state_db,
            registry_path=registry,
            strategy_id="trend_momentum",
            min_closed_trades_for_health=1,
        )
    )

    assert state_db.read_bytes() == before
    assert evidence.execution_mode == "shadow_paper"
    assert evidence.selected_closed_trade_count == 1
    assert evidence.paper_capital_trade_count_ignored == 1
    assert evidence.health_metrics_applied is True
    assert evidence.health.rolling_pf == pytest.approx(0.0)
    assert evidence.health.rolling_expectancy == pytest.approx(-1.0)
    assert "paper_capital_metrics_ignored_for_research_shadow_health" in evidence.warnings
    assert evidence.paper_capital_allowed is False
    assert evidence.live_allowed is False
    assert evidence.promotable is False


def test_health_evidence_with_small_shadow_sample_stays_non_authorizing(tmp_path: Path) -> None:
    state_db = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(state_db)
    _write_registry(registry)
    _insert_closed_pair(state_db, position_id="tiny-sample", execution_mode="shadow_paper", net_pnl=1.0)

    evidence = build_strategy_ledger_health_evidence(
        StrategyLedgerHealthEvidenceConfig(
            state_db_path=state_db,
            registry_path=registry,
            strategy_id="trend_momentum",
            min_closed_trades_for_health=2,
        )
    )

    assert evidence.selected_closed_trade_count == 1
    assert evidence.health_metrics_applied is False
    assert evidence.health.rolling_pf is None
    assert evidence.health.rolling_expectancy is None
    assert "insufficient_closed_trades_for_health:1/2" in evidence.warnings


def test_cli_uses_negative_shadow_health_only_to_kill_and_writes_optional_artifact(tmp_path: Path, capsys) -> None:
    state_db = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    output_dir = tmp_path / "reports"
    _create_state_db(state_db)
    _write_registry(registry)
    _insert_closed_pair(state_db, position_id="shadow-loss", execution_mode="shadow_paper", net_pnl=-1.0)
    before = state_db.read_bytes()

    exit_code = cli.main(
        [
            "strategy-autonomy-check",
            "--strategy-id", "trend_momentum",
            "--state-db", str(state_db),
            "--registry-path", str(registry),
            "--min-closed-trades-for-health", "1",
            "--output-dir", str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert state_db.read_bytes() == before
    assert payload["ledger_health_evidence"]["execution_mode"] == "shadow_paper"
    assert payload["ledger_health_evidence"]["health_metrics_applied"] is True
    assert payload["auto_kill_downgrade"]["decision"] == "KILL"
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["promotable"] is False
    artifact = Path(payload["ledger_health_evidence"]["json_report_path"])
    assert artifact.is_file()
    persisted = json.loads(artifact.read_text(encoding="utf-8"))
    assert persisted["json_report_path"] == str(artifact)
    assert persisted["paper_capital_allowed"] is False
    assert persisted["live_allowed"] is False


def test_health_evidence_import_boundary_excludes_execution_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/strategy_ledger_health_evidence.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.paper_trading",
        "autobot.v2.execution_engine",
    }
    assert imports.isdisjoint(forbidden)
