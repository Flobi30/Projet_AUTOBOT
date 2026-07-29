#!/usr/bin/env python3
"""Read-only observation diagnostics retained from the legacy paper tool.

This tool may summarize logs and write a preflight-only attestation artifact.
It contains no launch guidance, feature activation, private credential handling
or order path. Its historical name is retained for compatibility only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from autobot.v2.kill_switch import KillSwitch
from autobot.v2.startup_attestation import write_attestation_artifact


SIGNAL_PATTERNS = {
    "ranking_clues": ("ranking", "ranked", "score", "scored_universe"),
    "opportunity_clues": ("opportunity", "candidate", "spin-off", "spinoff"),
    "scaling_guard_clues": ("scalability", "guard", "scale", "freeze", "throttle"),
    "allocation_clues": ("allocator", "allocation", "capital", "reserve cash", "portfolio"),
    "universe_clues": ("universe", "eligible", "market selector"),
    "health_clues": ("health", "reconciliation", "ws stale", "latency", "heartbeat"),
}


def parse_timestamp_prefix(line: str) -> datetime | None:
    match = re.match(r"^(\d{4}-\d{2}-\d{2}[T ][^ ]+)", line)
    if not match:
        return None
    try:
        parsed = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    if counts.get("attestation_failed", 0) > 0 or counts.get("errors", 0) >= 10:
        return "critical"
    if (
        counts.get("errors", 0) > 0
        or counts.get("warnings", 0) >= 20
        or counts.get("kill_switch_mentions", 0) > 0
    ):
        return "degraded"
    return "stable"


def _read_status_artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {"error": f"status artifact not found: {path}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"error": f"failed to parse status artifact: {exc}"}
    return {
        key: payload[key]
        for key in ("status", "running", "health", "uptime", "message")
        if key in payload
    }


def summarize_session(
    log_file: Path,
    hours: int,
    status_artifact: Path | None = None,
) -> dict[str, Any]:
    """Read a log file only; it never starts or configures AUTOBOT."""

    if not log_file.exists():
        raise FileNotFoundError(f"log file not found: {log_file}")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    counts: Counter[str] = Counter()
    instance_names: set[str] = set()
    instance_symbols: set[str] = set()
    warnings: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    recent_warnings: list[str] = []
    recent_errors: list[str] = []
    start_ts: datetime | None = None
    end_ts: datetime | None = None

    with log_file.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            timestamp = parse_timestamp_prefix(line)
            if timestamp is not None and timestamp < since:
                continue
            if timestamp is not None:
                start_ts = timestamp if start_ts is None else min(start_ts, timestamp)
                end_ts = timestamp if end_ts is None else max(end_ts, timestamp)

            normalized = line.strip()
            lowered = normalized.lower()
            if "startup attestation passed" in lowered:
                counts["attestation_passed"] += 1
            if "startup attestation failed" in lowered:
                counts["attestation_failed"] += 1
            if "preflight_only=true" in lowered:
                counts["preflight_mentions"] += 1
            if "checks passed, trading not started" in lowered:
                counts["preflight_success"] += 1
            if "created:" in lowered and "observation" in lowered:
                counts["instances_created"] += 1
                match = re.search(r"created:\s*(.*?)\s*\(([^)]+)\)", normalized, re.IGNORECASE)
                if match:
                    instance_names.add(match.group(1).strip())
                    instance_symbols.add(match.group(2).strip())
            if "warning" in lowered:
                counts["warnings"] += 1
                warnings[normalized[:160]] += 1
                if len(recent_warnings) < 8:
                    recent_warnings.append(normalized)
            if "error" in lowered:
                counts["errors"] += 1
                errors[normalized[:160]] += 1
                if len(recent_errors) < 8:
                    recent_errors.append(normalized)
            if "kill switch" in lowered or "killswitch" in lowered or "kill-switch" in lowered:
                counts["kill_switch_mentions"] += 1
            for name, patterns in SIGNAL_PATTERNS.items():
                if any(pattern in lowered for pattern in patterns):
                    counts[name] += 1

    return {
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
        "top_warnings": [{"line": line, "count": count} for line, count in warnings.most_common(5)],
        "top_errors": [{"line": line, "count": count} for line, count in errors.most_common(5)],
        "recent_warnings": recent_warnings,
        "recent_errors": recent_errors,
        "signals": {name: counts.get(name, 0) for name in SIGNAL_PATTERNS},
        "status_artifact": _read_status_artifact(status_artifact),
    }


def cmd_validate(args: argparse.Namespace) -> int:
    """Refuse the retired activation flow without reading the supplied file."""

    if not Path(args.env_file).exists():
        raise FileNotFoundError(f"env file not found: {args.env_file}")
    print("Legacy paper environment validation is retired_from_execution.")
    print("No environment variables or credentials were read.")
    return 2


def cmd_session_summary(args: argparse.Namespace) -> int:
    summary = summarize_session(
        log_file=Path(args.log_file),
        hours=args.hours,
        status_artifact=Path(args.status_file) if args.status_file else None,
    )
    if args.json or args.format == "json":
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_readiness(args: argparse.Namespace) -> int:
    result = asyncio.run(
        write_attestation_artifact(
            artifact_path=args.artifact_file,
            preflight_only=True,
            kill_switch=KillSwitch(),
            order_executor=None,
        )
    )
    payload = json.loads(Path(args.artifact_file).read_text(encoding="utf-8"))
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"readiness_status={payload.get('status')} artifact={args.artifact_file}")
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOBOT observation diagnostics")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate", help="reject retired activation validation")
    validate.add_argument("--env-file", default=".env")
    validate.set_defaults(func=cmd_validate)

    summary = subcommands.add_parser("session-summary", help="summarize an existing log file")
    summary.add_argument("--log-file", default="autobot_async.log")
    summary.add_argument("--hours", type=int, default=24)
    summary.add_argument("--status-file", default="")
    summary.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    summary.add_argument("--json", action="store_true")
    summary.set_defaults(func=cmd_session_summary)

    readiness = subcommands.add_parser("readiness", help="write a preflight-only readiness artifact")
    readiness.add_argument("--artifact-file", default="artifacts/startup_attestation.json")
    readiness.add_argument("--format", choices=("text", "json"), default="text")
    readiness.set_defaults(func=cmd_readiness)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        return int(args.func(args))
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
