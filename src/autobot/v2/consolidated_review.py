"""Consolidated operator profitability review (Lot final analytics pass).

Combines:
- Decision Journal insights
- Pair attribution report
- Rejected opportunity analytics
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .decision_journal import build_rejected_opportunity_report
from .persistence import StatePersistence


def _read_decision_rows(journal_path: str, window_hours: Optional[int] = None) -> List[Dict[str, Any]]:
    path = Path(journal_path)
    if not path.exists():
        return []

    cutoff = None
    now = datetime.now(timezone.utc).timestamp()
    if window_hours is not None and int(window_hours) > 0:
        cutoff = now - int(window_hours) * 3600

    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if cutoff is not None:
            ts = str(rec.get("timestamp") or "")
            if ts:
                try:
                    dts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dts.timestamp() < cutoff:
                        continue
                except Exception:
                    pass
        rows.append(rec)
    return rows


def build_consolidated_profitability_review(
    *,
    db_path: str,
    journal_path: str,
    window_hours: Optional[int] = None,
    pair_limit: Optional[int] = 20,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    persistence = StatePersistence(db_path=db_path)
    pair_report = persistence.get_pair_attribution_report(window_hours=window_hours, limit=pair_limit)
    rejected = build_rejected_opportunity_report(journal_path=journal_path, window_hours=window_hours)

    journal_rows = _read_decision_rows(journal_path=journal_path, window_hours=window_hours)
    by_type: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for row in journal_rows:
        d = str(row.get("decision_type") or "unknown")
        s = str(row.get("source") or "unknown")
        by_type[d] = by_type.get(d, 0) + 1
        by_source[s] = by_source.get(s, 0) + 1

    top_winners = sorted(
        pair_report.get("pairs", []),
        key=lambda p: float(p.get("total_realized_pnl", 0.0)),
        reverse=True,
    )[:3]
    top_losers = sorted(
        pair_report.get("pairs", []),
        key=lambda p: float(p.get("total_realized_pnl", 0.0)),
    )[:3]

    recommendations: List[str] = []
    if not journal_rows:
        recommendations.append("No Decision Journal records found; verify ENABLE_DECISION_JOURNAL and journal path.")
    if int(pair_report.get("totals", {}).get("total_trades", 0)) == 0:
        recommendations.append("No realized closing trades in ledger; verify paper run activity and trade_ledger ingestion.")
    if float(pair_report.get("totals", {}).get("total_realized_pnl", 0.0)) < 0:
        recommendations.append("Net realized PnL is negative; inspect top losing pairs first for sizing/risk drift.")
    if rejected.get("by_reason"):
        top_reason = next(iter(rejected["by_reason"].items()))
        recommendations.append(
            f"Most frequent rejection reason is '{top_reason[0]}' ({top_reason[1]}x); inspect its gate thresholds and runtime context."
        )
    if not recommendations:
        recommendations.append("Review looks balanced; continue monitoring pair winners/losers and rejection reason concentration.")

    return {
        "generated_at": now.isoformat(),
        "window_hours": int(window_hours) if window_hours is not None else None,
        "decision_journal_insights": {
            "total_records": len(journal_rows),
            "by_decision_type": dict(sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)),
            "by_source": dict(sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)),
        },
        "pair_performance_attribution": pair_report,
        "rejected_opportunity_analytics": rejected,
        "highlights": {
            "top_winners": top_winners,
            "top_losers": top_losers,
        },
        "recommended_next_inspection_points": recommendations,
    }
