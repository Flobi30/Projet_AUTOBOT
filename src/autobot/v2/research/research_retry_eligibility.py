"""Research-only evidence gate for materially changed derivatives data.

This module never starts a runner and never changes research memory or the
experiment registry.  It answers a deliberately narrower question: can a
*new, explicitly named* research campaign be registered because a previously
unavailable derivatives capability is now demonstrably present?

The answer is not permission to rerun a hypothesis.  In particular, an old
negative result remains authoritative unless the newer terminal result carries
a comparable prior data signature that proves a material change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .data_capability_scanner import DataCapability
from .research_memory_store import ResearchMemoryStore


TERMINAL_RESEARCH_STATUSES = {
    "REJECT",
    "REJECTED",
    "REJECT_FAST",
    "REJECTED_CURRENT_CONFIG",
    "NO_GO",
    "DATA_MISSING",
    "INSUFFICIENT_DATA",
}
REQUIRED_CAPABILITIES_BY_HYPOTHESIS: dict[str, tuple[str, ...]] = {
    "funding_basis": ("funding_rates", "spot_perp_basis"),
}
CONTEXT_CAPABILITIES_BY_HYPOTHESIS: dict[str, tuple[str, ...]] = {
    "funding_basis": ("open_interest",),
}
_CAMPAIGN_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,127}$")


@dataclass(frozen=True)
class MaterialDataSignature:
    """Stable, non-runtime summary of evidence needed to compare data states."""

    hypothesis_id: str
    capability_states: dict[str, dict[str, Any]]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRetryEligibilityReport:
    """A non-executable decision about a possible *new* research campaign."""

    hypothesis_id: str
    template_id: str
    selected_prior_run_id: str | None
    latest_terminal_run_id: str | None
    status: str
    reasons: tuple[str, ...]
    material_capability_gains: tuple[str, ...]
    current_signature: MaterialDataSignature
    prior_signature_available: bool
    predecessor_trial_count_floor: int
    research_campaign_id: str | None
    new_campaign_registration_allowed: bool
    scheduler_rerun_allowed: bool = False
    runner_execution_allowed: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    automatic_promotion_allowed: bool = False
    order_created: bool = False
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["material_capability_gains"] = list(self.material_capability_gains)
        payload["safety_notes"] = [
            "Research eligibility assessment only; it does not schedule or run an experiment.",
            "Research memory and experiment registry are read-only inputs to this assessment.",
            "A new campaign must be registered separately and remains subject to normal trial, holdout and gate controls.",
            "No shadow activation, paper capital, live trading, promotion, sizing or order path is enabled.",
            "Grid remains no-go.",
        ]
        return payload


def build_material_data_signature(
    *,
    hypothesis_id: str,
    capabilities: Sequence[DataCapability],
) -> MaterialDataSignature:
    """Build a deterministic capability signature without host-specific paths.

    Paths and freshness timestamps are intentionally excluded: moving an
    immutable snapshot between a laptop and VPS must not look like new market
    evidence.  Readiness, coverage and canonical quality are preserved.
    """

    required = (*REQUIRED_CAPABILITIES_BY_HYPOTHESIS.get(hypothesis_id, ()), *CONTEXT_CAPABILITIES_BY_HYPOTHESIS.get(hypothesis_id, ()))
    by_id = {item.capability_id: item for item in capabilities}
    states: dict[str, dict[str, Any]] = {}
    for capability_id in required:
        item = by_id.get(capability_id)
        if item is None:
            states[capability_id] = {"available": False, "quality_status": "missing", "blockers": ["capability_not_scanned"]}
            continue
        states[capability_id] = {
            "available": bool(item.available),
            "provider": item.provider,
            "symbols": sorted(item.symbols),
            "timeframes": sorted(item.timeframes),
            "start_at": item.start_at,
            "end_at": item.end_at,
            "row_count": int(item.row_count),
            "duplicate_count": int(item.duplicate_count),
            "gap_count": int(item.gap_count),
            "quality_status": item.quality_status,
            "proxy_status": item.proxy_status,
            "blockers": sorted(item.blockers),
        }
    fingerprint = _fingerprint({"hypothesis_id": hypothesis_id, "capability_states": states})
    return MaterialDataSignature(hypothesis_id=hypothesis_id, capability_states=states, fingerprint=fingerprint)


def load_research_memory_records(path: str | Path) -> tuple[dict[str, Any], ...]:
    """Read legacy JSON or append-only SQLite research memory without mutation."""

    memory_path = Path(path)
    if memory_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return tuple(ResearchMemoryStore(memory_path).latest_records())
    if not memory_path.exists():
        return ()
    payload = json.loads(memory_path.read_text(encoding="utf-8"))
    records = payload.get("records", ()) if isinstance(payload, Mapping) else ()
    return tuple(dict(item) for item in records if isinstance(item, Mapping))


def assess_research_retry_eligibility(
    *,
    hypothesis_id: str,
    template_id: str,
    capabilities: Sequence[DataCapability],
    memory_records: Iterable[Mapping[str, Any]],
    prior_run_id: str | None = None,
    research_campaign_id: str | None = None,
) -> ResearchRetryEligibilityReport:
    """Assess material-data eligibility without authorizing a rerun.

    A selected historical record can establish that a capability was explicitly
    missing.  It cannot override a later terminal result.  A later result only
    stops blocking when it contains a comparable stored material signature
    that differs from the current one.  This prevents cherry-picking an old
    ``INSUFFICIENT_DATA`` outcome to bypass a newer ``REJECT_FAST`` result.
    """

    normalized_hypothesis = str(hypothesis_id).strip().lower()
    normalized_template = str(template_id).strip().lower()
    signature = build_material_data_signature(hypothesis_id=normalized_hypothesis, capabilities=capabilities)
    matching = [
        dict(item)
        for item in memory_records
        if str(item.get("hypothesis_id") or "").strip().lower() == normalized_hypothesis
        and str(item.get("template_id") or "").strip().lower() == normalized_template
    ]
    terminal = [item for item in matching if _is_terminal(item)]
    selected = _select_prior_record(matching, prior_run_id)
    latest_terminal = terminal[-1] if terminal else None
    campaign = _normalize_campaign_id(research_campaign_id)
    reasons: list[str] = []
    gains: list[str] = []

    required = REQUIRED_CAPABILITIES_BY_HYPOTHESIS.get(normalized_hypothesis)
    if not required:
        reasons.append("hypothesis_has_no_versioned_material_data_requirements")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_UNSUPPORTED_HYPOTHESIS",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )
    missing_now = [capability_id for capability_id in required if not bool(signature.capability_states[capability_id]["available"])]
    if missing_now:
        reasons.extend(f"current_required_capability_missing:{capability_id}" for capability_id in missing_now)
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_CURRENT_REQUIRED_DATA_MISSING",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )
    if selected is None:
        reasons.append("no_matching_prior_research_record")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_NO_PRIOR_RECORD_TO_COMPARE",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )
    if not _is_terminal(selected):
        reasons.append("selected_prior_record_is_not_terminal")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_PRIOR_RECORD_NOT_TERMINAL",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )

    if _is_performance_rejection(selected):
        reasons.append("prior_terminal_result_rejected_for_performance_not_missing_data")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_PRIOR_PERFORMANCE_REJECTION",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )

    selected_gains = _explicit_capability_gains(selected, signature)
    gains.extend(selected_gains)
    if not selected_gains:
        reasons.append("prior_record_does_not_prove_a_required_capability_transition")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "BLOCKED_NO_VERIFIED_MATERIAL_DATA_CHANGE",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )

    if latest_terminal is not None and latest_terminal is not selected:
        if _is_performance_rejection(latest_terminal):
            reasons.append("later_terminal_result_rejected_for_performance_not_missing_data")
            return _report(
                normalized_hypothesis,
                normalized_template,
                selected,
                latest_terminal,
                "BLOCKED_LATER_PERFORMANCE_REJECTION",
                reasons,
                gains,
                signature,
                campaign,
                matching,
            )
        latest_signature = _stored_material_signature(latest_terminal)
        if latest_signature is None or latest_signature.get("fingerprint") == signature.fingerprint:
            reasons.append("later_terminal_result_requires_a_verified_post_rejection_data_signature")
            return _report(
                normalized_hypothesis,
                normalized_template,
                selected,
                latest_terminal,
                "BLOCKED_LATER_TERMINAL_REQUIRES_VERIFIED_DATA_DELTA",
                reasons,
                gains,
                signature,
                campaign,
                matching,
            )
        reasons.append("later_terminal_result_has_a_distinct_recorded_data_signature")

    if campaign is None:
        reasons.append("explicit_research_campaign_id_required")
        return _report(
            normalized_hypothesis,
            normalized_template,
            selected,
            latest_terminal,
            "MATERIAL_CHANGE_DETECTED_NEW_CAMPAIGN_REQUIRED",
            reasons,
            gains,
            signature,
            campaign,
            matching,
        )

    reasons.extend(
        (
            "new_campaign_must_be_registered_with_current_signature_and_counted_trials",
            "normal_data_check_net_smoke_walk_forward_stress_and_holdout_gates_still_apply",
        )
    )
    return _report(
        normalized_hypothesis,
        normalized_template,
        selected,
        latest_terminal,
        "NEW_CAMPAIGN_ELIGIBLE_RESEARCH_ONLY",
        reasons,
        gains,
        signature,
        campaign,
        matching,
        new_campaign_registration_allowed=True,
    )


def write_research_retry_eligibility_report(
    report: ResearchRetryEligibilityReport,
    output_dir: str | Path,
    *,
    run_id: str,
) -> tuple[Path, Path]:
    """Write compact audit evidence; never write research memory or registry."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_id).strip()).strip("_") or "research_retry_eligibility"
    json_path = output / f"{safe_run_id}_research_retry_eligibility.json"
    markdown_path = output / f"{safe_run_id}_research_retry_eligibility.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _report(
    hypothesis_id: str,
    template_id: str,
    selected: Mapping[str, Any] | None,
    latest_terminal: Mapping[str, Any] | None,
    status: str,
    reasons: Sequence[str],
    gains: Sequence[str],
    signature: MaterialDataSignature,
    campaign: str | None,
    matching_records: Sequence[Mapping[str, Any]],
    *,
    new_campaign_registration_allowed: bool = False,
) -> ResearchRetryEligibilityReport:
    return ResearchRetryEligibilityReport(
        hypothesis_id=hypothesis_id,
        template_id=template_id,
        selected_prior_run_id=str(selected.get("run_id")) if selected else None,
        latest_terminal_run_id=str(latest_terminal.get("run_id")) if latest_terminal else None,
        status=status,
        reasons=tuple(dict.fromkeys(str(item) for item in reasons)),
        material_capability_gains=tuple(dict.fromkeys(str(item) for item in gains)),
        current_signature=signature,
        prior_signature_available=_stored_material_signature(latest_terminal or selected or {}) is not None,
        predecessor_trial_count_floor=sum(max(1, int(item.get("variant_count") or 1)) for item in matching_records),
        research_campaign_id=campaign,
        new_campaign_registration_allowed=new_campaign_registration_allowed,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _select_prior_record(records: Sequence[Mapping[str, Any]], prior_run_id: str | None) -> Mapping[str, Any] | None:
    if prior_run_id:
        wanted = str(prior_run_id).strip()
        return next((item for item in records if str(item.get("run_id") or "") == wanted), None)
    terminal = [item for item in records if _is_terminal(item)]
    return terminal[-1] if terminal else (records[-1] if records else None)


def _is_terminal(record: Mapping[str, Any]) -> bool:
    return str(record.get("final_status") or "").strip().upper() in TERMINAL_RESEARCH_STATUSES


def _is_performance_rejection(record: Mapping[str, Any]) -> bool:
    """Only data insufficiency may support a future materially-new campaign.

    A negative PF/edge outcome is a rejection of the economic thesis for the
    tested template.  More rows alone are not a licence to parameter-fish it
    again; a distinct thesis or template must go through separate governance.
    """

    return str(record.get("final_status") or "").strip().upper() in {
        "REJECT",
        "REJECTED",
        "REJECT_FAST",
        "REJECTED_CURRENT_CONFIG",
        "NO_GO",
    }


def _explicit_capability_gains(record: Mapping[str, Any], signature: MaterialDataSignature) -> list[str]:
    text = " ".join(
        str(item).upper()
        for item in (
            *(record.get("rejection_reasons") or ()),
            *((record.get("metrics") or {}).get("blockers") or ()),
        )
    )
    gained: list[str] = []
    mapping = {
        "spot_perp_basis": ("BASIS_HISTORY_WAITING", "BASIS_DATA_MISSING", "SPOT_PERP_BASIS_MISSING"),
        "open_interest": ("OPEN_INTEREST_HISTORY_WAITING", "OPEN_INTEREST_HISTORY_MISSING", "OPEN_INTEREST_MISSING"),
        "funding_rates": ("FUNDING_RATES_MISSING", "FUNDING_DATA_MISSING"),
    }
    for capability_id, markers in mapping.items():
        if any(marker in text for marker in markers) and bool(signature.capability_states.get(capability_id, {}).get("available")):
            gained.append(capability_id)
    return gained


def _stored_material_signature(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for container in (record.get("data_snapshot"), record.get("metrics")):
        if not isinstance(container, Mapping):
            continue
        candidate = container.get("material_data_signature")
        if isinstance(candidate, Mapping) and str(candidate.get("fingerprint") or "").strip():
            return candidate
    return None


def _normalize_campaign_id(value: str | None) -> str | None:
    campaign = str(value or "").strip().lower()
    if not campaign:
        return None
    if not _CAMPAIGN_ID.fullmatch(campaign):
        raise ValueError("research_campaign_id must contain 3-128 lowercase letters, digits, _, . or -")
    return campaign


def _fingerprint(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _render_markdown(report: ResearchRetryEligibilityReport) -> str:
    gains = tuple(f"- `{item}`" for item in report.material_capability_gains) or ("- None",)
    lines = [
        f"# Research Retry Eligibility — {report.hypothesis_id}",
        "",
        f"- Status: `{report.status}`",
        f"- Selected prior run: `{report.selected_prior_run_id or '-'} `",
        f"- Latest terminal run: `{report.latest_terminal_run_id or '-'} `",
        f"- Current material signature: `{report.current_signature.fingerprint}`",
        f"- Predecessor trial-count floor: `{report.predecessor_trial_count_floor}`",
        f"- New campaign registration allowed: `{report.new_campaign_registration_allowed}`",
        "- Scheduler rerun allowed: `False`",
        "- Runner execution allowed: `False`",
        "- Paper/live/promotion allowed: `False`",
        "",
        "## Material capability gains",
        *gains,
        "",
        "## Reasons",
        *(f"- `{item}`" for item in report.reasons),
        "",
        "## Safety",
        "- This assessment is read-only and cannot relaunch a hypothesis.",
        "- A separately registered campaign must still pass every normal research and holdout gate.",
        "- No shadow, paper, live, promotion, sizing, leverage or order path is enabled.",
    ]
    return "\n".join(lines) + "\n"
