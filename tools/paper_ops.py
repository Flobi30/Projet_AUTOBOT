#!/usr/bin/env python3
"""Operational helpers for AUTOBOT paper-trading mode.

Lightweight operator tooling only (no trading logic changes):
- Pre-launch validation for paper-safe environment settings.
- Start/run guidance output for operators.
- Post-run session summary extracted from bot logs.
- Feature-flag activation guidance for paper mode.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists():
    sys.path.insert(0, str(_SRC_DIR))

TRUE_VALUES = {"1", "true", "yes", "on"}

PAPER_REQUIRED = {
    "DEPLOYMENT_STAGE": "paper",
    "PAPER_TRADING": "true",
}

PAPER_RECOMMENDED = {
    "LIVE_TRADING_CONFIRMATION": "false",
    "API_KEY_ASSIGNMENT_MODE": "dedicated",
    "AUTOBOT_SAFE_MODE": "true",
}

PAPER_FEATURE_FLAGS = {
    "ENABLE_UNIVERSE_MANAGER": "false",
    "ENABLE_PAIR_RANKING_ENGINE": "false",
    "ENABLE_SCALABILITY_GUARD": "false",
    "ENABLE_INSTANCE_ACTIVATION_MANAGER": "false",
    "ENABLE_PORTFOLIO_ALLOCATOR": "false",
    "ENABLE_SHADOW_TRADING": "true",
    "ENABLE_VALIDATION_GUARD": "true",
}

SIGNAL_PATTERNS = {
    "ranking_clues": ("ranking", "ranked", "score", "scored_universe"),
    "opportunity_clues": ("opportunity", "candidate", "spin-off", "spinoff"),
    "scaling_guard_clues": ("scalability", "guard", "scale", "freeze", "throttle"),
    "allocation_clues": ("allocator", "allocation", "capital", "reserve cash", "portfolio"),
    "universe_clues": ("universe", "eligible", "market selector"),
    "health_clues": ("health", "reconciliation", "ws stale", "latency", "heartbeat"),
}


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")

    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip("\"'")
    return values


def merged_env(env_file_values: Dict[str, str]) -> Dict[str, str]:
    merged = dict(env_file_values)
    for key, value in os.environ.items():
        merged[key] = value
    return merged


def _bool(value: str) -> bool:
    return value.strip().lower() in TRUE_VALUES


def validate_paper_env(env_values: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    infos: List[str] = []

    for key, expected in PAPER_REQUIRED.items():
        got = env_values.get(key, "")
        if got.strip().lower() != expected:
            errors.append(f"{key} must be '{expected}' for paper mode (current: '{got or '<unset>'}')")

    for key, expected in PAPER_RECOMMENDED.items():
        got = env_values.get(key, "")
        if got and got.strip().lower() != expected:
            warnings.append(f"{key} recommended '{expected}' for paper mode (current: '{got}')")

    for key in ("KRAKEN_API_KEY", "KRAKEN_API_SECRET"):
        if not env_values.get(key):
            warnings.append(f"{key} not set; startup attestation may fail against exchange endpoints")

    marker = env_values.get("SECRET_EXPOSURE_MARKER_PATH", "data/compromised_secret.marker")
    if Path(marker).exists():
        errors.append(f"compromised marker exists: {marker} (startup attestation will block)")

    pairs = env_values.get("TRADING_PAIRS", "").strip()
    symbol = env_values.get("TRADING_SYMBOL", "").strip()
    if not pairs and not symbol:
        warnings.append("TRADING_PAIRS / TRADING_SYMBOL unset; defaults to XXBTZEUR")
    else:
        pair_list = [p.strip() for p in pairs.split(",") if p.strip()] or [symbol]
        infos.append(f"configured symbols: {', '.join(pair_list)}")

    initial_capital = env_values.get("INITIAL_CAPITAL", "").strip()
    if initial_capital:
        try:
            capital = float(initial_capital)
            if capital <= 0:
                errors.append("INITIAL_CAPITAL must be > 0")
            elif capital < 100:
                warnings.append(f"INITIAL_CAPITAL is low ({capital:.2f}); paper results may be noisy")
            else:
                infos.append(f"initial capital: {capital:.2f}")
        except ValueError:
            errors.append(f"INITIAL_CAPITAL invalid float: '{initial_capital}'")

    if _bool(env_values.get("AUTOBOT_FORCE_ENABLE_ALL", "false")):
        warnings.append("AUTOBOT_FORCE_ENABLE_ALL=true can override selective feature flags")

    return errors, warnings, infos


def print_start_guide() -> None:
    print("PAPER TRADING START GUIDE")
    print("=" * 28)
    print("1) Validate environment")
    print("   python tools/paper_ops.py validate --env-file .env")
    print("")
    print("2) Run preflight attestation only")
    print("   PREFLIGHT_ONLY=true python -u src/autobot/v2/main_async.py")
    print("")
    print("3) Launch paper session")
    print("   PAPER_TRADING=true DEPLOYMENT_STAGE=paper python -u src/autobot/v2/main_async.py")
    print("")
    print("4) Observe in another terminal")
    print("   tail -f autobot_async.log")
    print("   curl -s http://127.0.0.1:8080/api/status")
    print("")
    print("5) End-of-session summary")
    print("   python tools/paper_ops.py session-summary --log-file autobot_async.log --hours 24 --format markdown")


def parse_timestamp_prefix(line: str) -> datetime | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[T ][^ ]+)", line)
    if not m:
        return None
    candidate = m.group(1).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _normalize_line_for_top(line: str) -> str:
    clean = re.sub(r"\s+", " ", line.strip())
    return clean[:160]


def _attestation_state(counts: Counter[str]) -> str:
    if counts.get("attestation_failed", 0) > 0:
        return "failed"
    if counts.get("attestation_passed", 0) > 0:
        return "passed"
    return "unknown"


def _preflight_state(counts: Counter[str]) -> str:
    if counts.get("preflight_success", 0) > 0:
        return "passed"
    if counts.get("preflight_mentions", 0) > 0:
        return "mentioned"
    return "unknown"


def _session_health(counts: Counter[str]) -> str:
    errors = counts.get("errors", 0)
    warnings = counts.get("warnings", 0)
    if counts.get("attestation_failed", 0) > 0 or errors >= 10:
        return "critical"
    if errors > 0 or warnings >= 20 or counts.get("kill_switch_mentions", 0) > 0:
        return "degraded"
    return "stable"


def _hints(summary: Dict[str, Any]) -> List[str]:
    counts: Dict[str, int] = summary.get("counts", {})
    hints: List[str] = []

    if summary.get("attestation", {}).get("status") != "passed":
        hints.append("Re-run PREFLIGHT_ONLY and verify startup attestation + exchange connectivity checks.")

    if counts.get("errors", 0) > 0:
        hints.append("Inspect top error lines first, then full logs around their timestamps.")

    if counts.get("kill_switch_mentions", 0) > 0:
        hints.append("Review kill-switch/reconciliation events and confirm no persistent drift or API failure pattern.")

    if counts.get("instances_created", 0) == 0:
        hints.append("No instance creation observed; verify TRADING_PAIRS/TRADING_SYMBOL and instance startup path.")

    if counts.get("ranking_clues", 0) == 0:
        hints.append("No ranking clues found; if expected, verify ENABLE_PAIR_RANKING_ENGINE and related modules.")

    if counts.get("scaling_guard_clues", 0) == 0:
        hints.append("No scaling/guard clues found; if expected, verify ENABLE_SCALABILITY_GUARD and guard logs.")

    status = summary.get("status_artifact", {})
    if status and "error" in status:
        hints.append("Status artifact parse failed; verify exported status JSON is valid.")

    if not hints:
        hints.append("Session looks stable. Keep monitoring warnings trend and instance activity over longer windows.")

    return hints


def _read_status_artifact(path: Path | None) -> Dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {"error": f"status artifact not found: {path}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - best effort parser
        return {"error": f"failed to parse status artifact: {exc}"}

    status: Dict[str, Any] = {"source": str(path)}
    for key in ("status", "running", "paper_mode", "health", "uptime", "message"):
        if key in payload:
            status[key] = payload.get(key)

    instances = payload.get("instances")
    if isinstance(instances, list):
        status["instances_count"] = len(instances)
    if "active_instances" in payload:
        status["active_instances"] = payload.get("active_instances")

    return status


def summarize_session(log_file: Path, hours: int, status_artifact: Path | None = None) -> Dict[str, Any]:
    if not log_file.exists():
        raise FileNotFoundError(f"log file not found: {log_file}")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    counts: Counter[str] = Counter()
    recent_errors: List[str] = []
    recent_warnings: List[str] = []
    instance_names: set[str] = set()
    instance_symbols: set[str] = set()
    top_error_counter: Counter[str] = Counter()
    top_warning_counter: Counter[str] = Counter()
    start_ts: datetime | None = None
    end_ts: datetime | None = None

    with log_file.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            ts = parse_timestamp_prefix(line)
            if ts is not None and ts < since:
                continue
            if ts is not None:
                start_ts = ts if start_ts is None else min(start_ts, ts)
                end_ts = ts if end_ts is None else max(end_ts, ts)

            l = line.strip()
            lo = l.lower()

            if "startup attestation passed" in lo:
                counts["attestation_passed"] += 1
            if "startup attestation failed" in lo:
                counts["attestation_failed"] += 1
            if "preflight_only=true" in lo:
                counts["preflight_mentions"] += 1
            if "checks passed, trading not started" in lo:
                counts["preflight_success"] += 1

            if "created:" in lo and "grid" in lo:
                counts["instances_created"] += 1
                m = re.search(r"created:\s*(.*?)\s*\(([^)]+)\)", l, flags=re.IGNORECASE)
                if m:
                    instance_names.add(m.group(1).strip())
                    instance_symbols.add(m.group(2).strip())

            if "warning" in lo:
                counts["warnings"] += 1
                norm = _normalize_line_for_top(l)
                top_warning_counter[norm] += 1
                if len(recent_warnings) < 8:
                    recent_warnings.append(l)
            if "error" in lo:
                counts["errors"] += 1
                norm = _normalize_line_for_top(l)
                top_error_counter[norm] += 1
                if len(recent_errors) < 8:
                    recent_errors.append(l)

            if "kill switch" in lo or "killswitch" in lo or "kill-switch" in lo:
                counts["kill_switch_mentions"] += 1
            if "paper_trading=true" in lo or "paper trading" in lo:
                counts["paper_mode_mentions"] += 1

            for signal_name, patterns in SIGNAL_PATTERNS.items():
                if any(p in lo for p in patterns):
                    counts[signal_name] += 1

    status = _read_status_artifact(status_artifact)

    summary: Dict[str, Any] = {
        "window_hours": hours,
        "log_file": str(log_file),
        "analysis_window": {
            "start_utc": start_ts.isoformat() if start_ts else None,
            "end_utc": end_ts.isoformat() if end_ts else None,
        },
        "counts": dict(counts),
        "attestation": {
            "status": _attestation_state(counts),
            "passed_mentions": counts.get("attestation_passed", 0),
            "failed_mentions": counts.get("attestation_failed", 0),
            "preflight_status": _preflight_state(counts),
        },
        "instances": {
            "created_mentions": counts.get("instances_created", 0),
            "unique_names": sorted(instance_names),
            "unique_symbols": sorted(instance_symbols),
        },
        "session_health": {
            "level": _session_health(counts),
            "warnings": counts.get("warnings", 0),
            "errors": counts.get("errors", 0),
            "kill_switch_mentions": counts.get("kill_switch_mentions", 0),
        },
        "top_warnings": [{"line": k, "count": v} for k, v in top_warning_counter.most_common(5)],
        "top_errors": [{"line": k, "count": v} for k, v in top_error_counter.most_common(5)],
        "recent_warnings": recent_warnings,
        "recent_errors": recent_errors,
        "signals": {k: counts.get(k, 0) for k in SIGNAL_PATTERNS.keys()},
        "status_artifact": status,
    }
    summary["next_steps"] = _hints(summary)
    return summary


def _render_session_summary_text(summary: Dict[str, Any]) -> str:
    counts = summary.get("counts", {})
    attestation = summary.get("attestation", {})
    instances = summary.get("instances", {})
    health = summary.get("session_health", {})
    signals = summary.get("signals", {})

    lines = ["PAPER SESSION SUMMARY", "=" * 21]
    lines.append(f"Window: last {summary.get('window_hours')}h")
    aw = summary.get("analysis_window", {})
    lines.append(f"Log range UTC: {aw.get('start_utc')} → {aw.get('end_utc')}")
    lines.append(f"Session health: {health.get('level')}")

    lines.append("\nCore signals:")
    for key in ("warnings", "errors", "kill_switch_mentions", "paper_mode_mentions"):
        lines.append(f"- {key}: {counts.get(key, 0)}")

    lines.append("\nAttestation / preflight:")
    lines.append(f"- attestation: {attestation.get('status')}")
    lines.append(f"- preflight: {attestation.get('preflight_status')}")

    lines.append("\nInstances:")
    lines.append(f"- created_mentions: {instances.get('created_mentions', 0)}")
    lines.append(f"- unique_symbols: {', '.join(instances.get('unique_symbols', [])) or 'none'}")

    lines.append("\nAdvanced paper clues:")
    for key in sorted(signals.keys()):
        lines.append(f"- {key}: {signals[key]}")

    top_errors = summary.get("top_errors", [])
    if top_errors:
        lines.append("\nTop errors:")
        for item in top_errors:
            lines.append(f"- ({item['count']}x) {item['line']}")

    top_warnings = summary.get("top_warnings", [])
    if top_warnings:
        lines.append("\nTop warnings:")
        for item in top_warnings:
            lines.append(f"- ({item['count']}x) {item['line']}")

    status = summary.get("status_artifact", {})
    if status:
        lines.append("\nStatus artifact snapshot:")
        for k in sorted(status.keys()):
            lines.append(f"- {k}: {status[k]}")

    lines.append("\nWhat to inspect next:")
    for hint in summary.get("next_steps", []):
        lines.append(f"- {hint}")

    return "\n".join(lines)


def _render_session_summary_markdown(summary: Dict[str, Any]) -> str:
    attestation = summary.get("attestation", {})
    instances = summary.get("instances", {})
    health = summary.get("session_health", {})
    counts = summary.get("counts", {})
    signals = summary.get("signals", {})
    aw = summary.get("analysis_window", {})

    lines = [
        "# Paper Session Summary",
        "",
        f"- **Window:** last `{summary.get('window_hours')}h`",
        f"- **Log file:** `{summary.get('log_file')}`",
        f"- **Log range (UTC):** `{aw.get('start_utc')}` → `{aw.get('end_utc')}`",
        f"- **Session health:** **{health.get('level', 'unknown').upper()}**",
        "",
        "## Core Signals",
        f"- Warnings: `{counts.get('warnings', 0)}`",
        f"- Errors: `{counts.get('errors', 0)}`",
        f"- Kill-switch mentions: `{counts.get('kill_switch_mentions', 0)}`",
        f"- Paper-mode mentions: `{counts.get('paper_mode_mentions', 0)}`",
        "",
        "## Attestation / Preflight",
        f"- Attestation status: `{attestation.get('status')}`",
        f"- Attestation passed mentions: `{attestation.get('passed_mentions', 0)}`",
        f"- Attestation failed mentions: `{attestation.get('failed_mentions', 0)}`",
        f"- Preflight status: `{attestation.get('preflight_status')}`",
        "",
        "## Instance Clues",
        f"- Creation mentions: `{instances.get('created_mentions', 0)}`",
        f"- Unique symbols: `{', '.join(instances.get('unique_symbols', [])) or 'none'}`",
        "",
        "## Advanced Clues",
    ]

    for key in sorted(signals.keys()):
        lines.append(f"- {key}: `{signals[key]}`")

    top_errors = summary.get("top_errors", [])
    if top_errors:
        lines.extend(["", "## Top Errors"])
        for item in top_errors:
            lines.append(f"- ({item['count']}x) `{item['line']}`")

    top_warnings = summary.get("top_warnings", [])
    if top_warnings:
        lines.extend(["", "## Top Warnings"])
        for item in top_warnings:
            lines.append(f"- ({item['count']}x) `{item['line']}`")

    status = summary.get("status_artifact", {})
    if status:
        lines.extend(["", "## Status Artifact Snapshot"])
        for key in sorted(status.keys()):
            lines.append(f"- {key}: `{status[key]}`")

    lines.extend(["", "## What to Inspect Next"])
    for hint in summary.get("next_steps", []):
        lines.append(f"- {hint}")

    return "\n".join(lines)


def print_flags_guide() -> None:
    print("PAPER MODE FEATURE-FLAG GUIDE")
    print("=" * 30)
    print("Set explicitly in .env to avoid ambiguity during operations:")
    print("")
    for k, v in PAPER_REQUIRED.items():
        print(f"{k}={v}   # required")
    for k, v in PAPER_RECOMMENDED.items():
        print(f"{k}={v}   # recommended")
    print("")
    print("Feature toggles (safe baseline for current paper operations pass):")
    for k, v in PAPER_FEATURE_FLAGS.items():
        print(f"{k}={v}")
    print("")
    print("Note: if AUTOBOT_FORCE_ENABLE_ALL=true, selective flags may be overridden.")


def _render_pair_attribution_text(report: Dict[str, Any]) -> str:
    lines = ["PAIR PERFORMANCE ATTRIBUTION", "=" * 28]
    lines.append(f"Generated at: {report.get('generated_at')}")
    lines.append(f"Window hours: {report.get('window_hours')}")
    totals = report.get("totals", {})
    lines.append(
        "Totals: trades={trades} pnl={pnl:+.2f} fees={fees:.2f}".format(
            trades=int(totals.get("total_trades", 0)),
            pnl=float(totals.get("total_realized_pnl", 0.0)),
            fees=float(totals.get("total_fees", 0.0)),
        )
    )
    lines.append("")
    for p in report.get("pairs", []):
        lines.append(
            "{symbol}: trades={trades} W/L={wins}/{losses} pnl={pnl:+.2f} fees={fees:.2f} "
            "PF={pf:.2f} win_rate={wr:.1%} expectancy={exp:+.2f} recent24h={r24}".format(
                symbol=p.get("symbol"),
                trades=int(p.get("total_trades", 0)),
                wins=int(p.get("wins", 0)),
                losses=int(p.get("losses", 0)),
                pnl=float(p.get("total_realized_pnl", 0.0)),
                fees=float(p.get("total_fees", 0.0)),
                pf=float(p.get("profit_factor", 0.0)),
                wr=float(p.get("win_rate", 0.0)),
                exp=float(p.get("expectancy", 0.0)),
                r24=int(p.get("recent_trades_24h", 0)),
            )
        )
    if not report.get("pairs"):
        lines.append("No pair attribution data available in selected window.")
    return "\n".join(lines)


def _render_pair_attribution_markdown(report: Dict[str, Any]) -> str:
    totals = report.get("totals", {})
    lines = [
        "# Pair Performance Attribution",
        "",
        f"- **Generated at:** `{report.get('generated_at')}`",
        f"- **Window hours:** `{report.get('window_hours')}`",
        f"- **Pair count:** `{report.get('pair_count')}`",
        f"- **Total trades:** `{int(totals.get('total_trades', 0))}`",
        f"- **Total realized PnL:** `{float(totals.get('total_realized_pnl', 0.0)):+.2f}`",
        f"- **Total fees:** `{float(totals.get('total_fees', 0.0)):.2f}`",
        "",
    ]
    pairs = report.get("pairs", [])
    if not pairs:
        lines.append("_No pair attribution data available in selected window._")
        return "\n".join(lines)

    lines.extend(
        [
            "| Symbol | Trades | Wins | Losses | Realized PnL | Fees | PF | Win rate | Expectancy | Recent 24h | Last trade |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for p in pairs:
        lines.append(
            "| {symbol} | {trades} | {wins} | {losses} | {pnl:+.2f} | {fees:.2f} | {pf:.2f} | {wr:.1%} | {exp:+.2f} | {r24} | {last} |".format(
                symbol=p.get("symbol"),
                trades=int(p.get("total_trades", 0)),
                wins=int(p.get("wins", 0)),
                losses=int(p.get("losses", 0)),
                pnl=float(p.get("total_realized_pnl", 0.0)),
                fees=float(p.get("total_fees", 0.0)),
                pf=float(p.get("profit_factor", 0.0)),
                wr=float(p.get("win_rate", 0.0)),
                exp=float(p.get("expectancy", 0.0)),
                r24=int(p.get("recent_trades_24h", 0)),
                last=p.get("last_trade_at") or "-",
            )
        )
    return "\n".join(lines)


def _render_rejected_opportunities_text(report: Dict[str, Any]) -> str:
    lines = ["REJECTED OPPORTUNITY ANALYTICS", "=" * 30]
    lines.append(f"Generated at: {report.get('generated_at')}")
    lines.append(f"Window hours: {report.get('window_hours')}")
    lines.append(f"Total rejections: {report.get('total_rejections')}")
    lines.append("")
    lines.append("By reason:")
    for reason, count in report.get("by_reason", {}).items():
        lines.append(f"- {reason}: {count}")
    lines.append("")
    lines.append("By symbol:")
    for symbol, count in report.get("by_symbol", {}).items():
        lines.append(f"- {symbol}: {count}")
    if not report.get("by_reason"):
        lines.append("No rejected opportunity records found.")
    return "\n".join(lines)


def _render_rejected_opportunities_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Rejected Opportunity Analytics",
        "",
        f"- **Generated at:** `{report.get('generated_at')}`",
        f"- **Window hours:** `{report.get('window_hours')}`",
        f"- **Total rejections:** `{report.get('total_rejections')}`",
        "",
        "## By Reason",
    ]
    by_reason = report.get("by_reason", {})
    if by_reason:
        for reason, count in by_reason.items():
            lines.append(f"- {reason}: `{count}`")
    else:
        lines.append("_No rejected opportunity records found._")
    lines.append("")
    lines.append("## By Symbol")
    by_symbol = report.get("by_symbol", {})
    if by_symbol:
        for symbol, count in by_symbol.items():
            lines.append(f"- {symbol}: `{count}`")
    else:
        lines.append("_No symbol-level rejection records found._")
    return "\n".join(lines)


def _render_profitability_review_text(report: Dict[str, Any]) -> str:
    lines = ["CONSOLIDATED PROFITABILITY REVIEW", "=" * 33]
    lines.append(f"Generated at: {report.get('generated_at')}")
    lines.append(f"Window hours: {report.get('window_hours')}")
    dj = report.get("decision_journal_insights", {})
    lines.append(f"Decision records: {dj.get('total_records', 0)}")
    pair_totals = report.get("pair_performance_attribution", {}).get("totals", {})
    lines.append(
        "Realized totals: trades={trades} pnl={pnl:+.2f} fees={fees:.2f}".format(
            trades=int(pair_totals.get("total_trades", 0)),
            pnl=float(pair_totals.get("total_realized_pnl", 0.0)),
            fees=float(pair_totals.get("total_fees", 0.0)),
        )
    )
    rej = report.get("rejected_opportunity_analytics", {})
    lines.append(f"Rejected opportunities: {rej.get('total_rejections', 0)}")
    lines.append("")
    lines.append("Top decision types:")
    for k, v in list(dj.get("by_decision_type", {}).items())[:5]:
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("Top rejection reasons:")
    for k, v in list(rej.get("by_reason", {}).items())[:5]:
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("Recommended next inspection points:")
    for r in report.get("recommended_next_inspection_points", []):
        lines.append(f"- {r}")
    return "\n".join(lines)


def _render_profitability_review_markdown(report: Dict[str, Any]) -> str:
    dj = report.get("decision_journal_insights", {})
    pair_totals = report.get("pair_performance_attribution", {}).get("totals", {})
    rej = report.get("rejected_opportunity_analytics", {})
    lines = [
        "# Consolidated Profitability Review",
        "",
        f"- **Generated at:** `{report.get('generated_at')}`",
        f"- **Window hours:** `{report.get('window_hours')}`",
        f"- **Decision records:** `{dj.get('total_records', 0)}`",
        f"- **Realized trades:** `{int(pair_totals.get('total_trades', 0))}`",
        f"- **Realized PnL:** `{float(pair_totals.get('total_realized_pnl', 0.0)):+.2f}`",
        f"- **Fees:** `{float(pair_totals.get('total_fees', 0.0)):.2f}`",
        f"- **Rejected opportunities:** `{rej.get('total_rejections', 0)}`",
        "",
        "## Top Decision Types",
    ]
    for k, v in list(dj.get("by_decision_type", {}).items())[:5]:
        lines.append(f"- {k}: `{v}`")
    if not dj.get("by_decision_type"):
        lines.append("_No decision records in selected window._")
    lines.append("")
    lines.append("## Top Rejection Reasons")
    for k, v in list(rej.get("by_reason", {}).items())[:5]:
        lines.append(f"- {k}: `{v}`")
    if not rej.get("by_reason"):
        lines.append("_No rejected opportunity records in selected window._")
    lines.append("")
    lines.append("## Recommended Next Inspection Points")
    for r in report.get("recommended_next_inspection_points", []):
        lines.append(f"- {r}")
    return "\n".join(lines)


def _render_autonomous_review_text(report: Dict[str, Any]) -> str:
    lines = ["AUTONOMOUS REVIEW (RECOMMENDATION-FIRST)", "=" * 40]
    lines.append(f"Generated at: {report.get('generated_at')}")
    lines.append(f"Window hours: {report.get('window_hours')}")
    lines.append(f"System health: {report.get('system_health')}")
    lines.append(f"Recommended action: {report.get('recommended_action')}")
    lines.append(f"Confidence: {report.get('confidence')}")
    lines.append("")
    lines.append("Top pairs:")
    for pair in report.get("top_pairs", []):
        lines.append(f"- {pair.get('symbol')}: pnl={float(pair.get('total_realized_pnl', 0.0)):+.2f}")
    lines.append("")
    lines.append("Bottom pairs:")
    for pair in report.get("bottom_pairs", []):
        lines.append(f"- {pair.get('symbol')}: pnl={float(pair.get('total_realized_pnl', 0.0)):+.2f}")
    lines.append("")
    lines.append("Top rejection reasons:")
    for item in report.get("top_rejection_reasons", []):
        lines.append(f"- {item.get('reason')}: {item.get('count')}")
    lines.append("")
    lines.append("Focus points:")
    for point in report.get("focus_points", []):
        lines.append(f"- {point}")
    return "\n".join(lines)


def _render_autonomous_review_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Autonomous Review (Recommendation-first)",
        "",
        f"- **Generated at:** `{report.get('generated_at')}`",
        f"- **Window hours:** `{report.get('window_hours')}`",
        f"- **System health:** `{report.get('system_health')}`",
        f"- **Recommended action:** `{report.get('recommended_action')}`",
        f"- **Confidence:** `{report.get('confidence')}`",
        "",
        "## Top Pairs",
    ]
    top_pairs = report.get("top_pairs", [])
    if top_pairs:
        for pair in top_pairs:
            lines.append(f"- {pair.get('symbol')}: `{float(pair.get('total_realized_pnl', 0.0)):+.2f}`")
    else:
        lines.append("_No positive pair performers in selected window._")
    lines.append("")
    lines.append("## Bottom Pairs")
    bottom_pairs = report.get("bottom_pairs", [])
    if bottom_pairs:
        for pair in bottom_pairs:
            lines.append(f"- {pair.get('symbol')}: `{float(pair.get('total_realized_pnl', 0.0)):+.2f}`")
    else:
        lines.append("_No losing pairs in selected window._")
    lines.append("")
    lines.append("## Top Rejection Reasons")
    reasons = report.get("top_rejection_reasons", [])
    if reasons:
        for item in reasons:
            lines.append(f"- {item.get('reason')}: `{item.get('count')}`")
    else:
        lines.append("_No rejection reasons in selected window._")
    lines.append("")
    lines.append("## Focus Points")
    for point in report.get("focus_points", []):
        lines.append(f"- {point}")
    return "\n".join(lines)


def cmd_validate(args: argparse.Namespace) -> int:
    env_values = parse_env_file(Path(args.env_file))
    merged = merged_env(env_values)
    errors, warnings, infos = validate_paper_env(merged)

    print("PAPER PRE-LAUNCH VALIDATION")
    print("=" * 28)
    for item in infos:
        print(f"INFO: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    for item in errors:
        print(f"ERROR: {item}")

    if errors:
        print(f"\nRESULT: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1

    print(f"\nRESULT: PASS ({len(warnings)} warning(s))")
    return 0


def cmd_session_summary(args: argparse.Namespace) -> int:
    summary = summarize_session(
        log_file=Path(args.log_file),
        hours=args.hours,
        status_artifact=Path(args.status_file) if args.status_file else None,
    )

    fmt = args.format
    if args.json:
        fmt = "json"

    if fmt == "json":
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif fmt == "markdown":
        print(_render_session_summary_markdown(summary))
    else:
        print(_render_session_summary_text(summary))

    return 0


def cmd_pair_attribution(args: argparse.Namespace) -> int:
    from autobot.v2.persistence import StatePersistence

    persistence = StatePersistence(db_path=args.db_path)
    report = persistence.get_pair_attribution_report(
        window_hours=args.window_hours,
        limit=args.limit,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(_render_pair_attribution_markdown(report))
    else:
        print(_render_pair_attribution_text(report))
    return 0


def cmd_rejected_opportunities(args: argparse.Namespace) -> int:
    from autobot.v2.decision_journal import build_rejected_opportunity_report

    report = build_rejected_opportunity_report(
        journal_path=args.journal_path,
        window_hours=args.window_hours,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(_render_rejected_opportunities_markdown(report))
    else:
        print(_render_rejected_opportunities_text(report))
    return 0


def cmd_profitability_review(args: argparse.Namespace) -> int:
    from autobot.v2.consolidated_review import build_consolidated_profitability_review

    report = build_consolidated_profitability_review(
        db_path=args.db_path,
        journal_path=args.journal_path,
        window_hours=args.window_hours,
        pair_limit=args.pair_limit,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(_render_profitability_review_markdown(report))
    else:
        print(_render_profitability_review_text(report))
    return 0


def cmd_autonomous_review(args: argparse.Namespace) -> int:
    from autobot.v2.autonomous_review import build_autonomous_review

    report = build_autonomous_review(
        db_path=args.db_path,
        journal_path=args.journal_path,
        window_hours=args.window_hours,
        pair_limit=args.pair_limit,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(_render_autonomous_review_markdown(report))
    else:
        print(_render_autonomous_review_text(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOBOT paper operations helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="validate paper-launch env safety")
    p_validate.add_argument("--env-file", default=".env", help="path to env file")
    p_validate.set_defaults(func=cmd_validate)

    p_guide = sub.add_parser("start-guide", help="print start/run guidance")
    p_guide.set_defaults(func=lambda _args: (print_start_guide() or 0))

    p_summary = sub.add_parser("session-summary", help="summarize recent log session")
    p_summary.add_argument("--log-file", default="autobot_async.log", help="log file to parse")
    p_summary.add_argument("--hours", type=int, default=24, help="rolling lookback window")
    p_summary.add_argument("--status-file", default="", help="optional JSON status snapshot artifact")
    p_summary.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="output format for operator report",
    )
    p_summary.add_argument("--json", action="store_true", help="deprecated alias for --format json")
    p_summary.set_defaults(func=cmd_session_summary)

    p_flags = sub.add_parser("flags-guide", help="print paper-mode feature flag guidance")
    p_flags.set_defaults(func=lambda _args: (print_flags_guide() or 0))

    p_attr = sub.add_parser("pair-attribution", help="pair-level realized pnl attribution report")
    p_attr.add_argument("--db-path", default="data/autobot_state.db", help="SQLite DB path")
    p_attr.add_argument("--window-hours", type=int, default=None, help="optional rolling lookback window")
    p_attr.add_argument("--limit", type=int, default=None, help="optional top-N pairs")
    p_attr.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p_attr.set_defaults(func=cmd_pair_attribution)

    p_rej = sub.add_parser("rejected-opportunities", help="grouped rejected opportunity analytics")
    p_rej.add_argument("--journal-path", default="data/decision_journal.jsonl", help="Decision journal JSONL path")
    p_rej.add_argument("--window-hours", type=int, default=None, help="optional rolling lookback window")
    p_rej.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p_rej.set_defaults(func=cmd_rejected_opportunities)

    p_review = sub.add_parser("profitability-review", help="consolidated profitability review across analytics")
    p_review.add_argument("--db-path", default="data/autobot_state.db", help="SQLite DB path")
    p_review.add_argument("--journal-path", default="data/decision_journal.jsonl", help="Decision journal JSONL path")
    p_review.add_argument("--window-hours", type=int, default=None, help="optional rolling lookback window")
    p_review.add_argument("--pair-limit", type=int, default=20, help="top-N pairs in attribution section")
    p_review.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p_review.set_defaults(func=cmd_profitability_review)

    p_auto = sub.add_parser("autonomous-review", help="autonomous recommendation-first analytics review")
    p_auto.add_argument("--db-path", default="data/autobot_state.db", help="SQLite DB path")
    p_auto.add_argument("--journal-path", default="data/decision_journal.jsonl", help="Decision journal JSONL path")
    p_auto.add_argument("--window-hours", type=int, default=None, help="optional rolling lookback window")
    p_auto.add_argument("--pair-limit", type=int, default=20, help="top-N pairs considered")
    p_auto.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    p_auto.set_defaults(func=cmd_autonomous_review)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
