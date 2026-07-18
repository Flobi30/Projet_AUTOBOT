"""Sealed, research-only evidence required before a shadow review can pass.

This boundary connects two independent research checks without importing a
strategy, scheduler, order router, paper engine, or broker client:

* a final, sealed holdout evaluated net of costs; and
* a conservative statistical summary that accounts for known trials.

It deliberately cannot promote an artifact, allocate paper capital, or enable
live trading.  A valid envelope merely permits the *existing* human-reviewed
shadow governance path to consider a passed ``SHADOW_REVIEW`` stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Mapping


SHADOW_REVIEW_EVIDENCE_SCHEMA_VERSION = 1
HOLDOUT_PASSED_VERDICT = "HOLDOUT_PASSED_RESEARCH_ONLY"
STATISTICAL_ELIGIBLE_DECISION = "SHADOW_REVIEW_ELIGIBLE"


class ShadowReviewEvidenceError(ValueError):
    """Raised when final-review evidence is incomplete, inconsistent, or unsafe."""


@dataclass(frozen=True)
class ShadowReviewEvidence:
    """Validated immutable facts for a research-only shadow review.

    ``holdout_evaluation`` and ``statistical_gate_summary`` preserve the
    producer outputs verbatim after their identity, safety flags and overlapping
    metrics have been checked.  The class is intentionally a contract boundary,
    not a second implementation of either calculation.
    """

    experiment_id: str
    holdout_evaluation: Mapping[str, Any]
    statistical_gate_summary: Mapping[str, Any]
    fingerprint: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        experiment_id = str(self.experiment_id or "").strip()
        if not experiment_id:
            raise ShadowReviewEvidenceError("experiment_id is required")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise ShadowReviewEvidenceError("shadow review evidence must remain research-only and non-promotional")
        holdout = _mapping(self.holdout_evaluation, "holdout_evaluation")
        statistical = _mapping(self.statistical_gate_summary, "statistical_gate_summary")
        _validate_holdout(holdout, experiment_id=experiment_id)
        _validate_statistical_summary(statistical)
        _validate_overlapping_metrics(holdout, statistical)
        expected = _fingerprint(_identity_payload(experiment_id, holdout, statistical))
        if str(self.fingerprint or "") != expected:
            raise ShadowReviewEvidenceError("shadow review evidence fingerprint does not match its contents")
        object.__setattr__(self, "experiment_id", experiment_id)
        object.__setattr__(self, "holdout_evaluation", holdout)
        object.__setattr__(self, "statistical_gate_summary", statistical)

    @property
    def trade_count(self) -> int:
        return int(self.holdout_evaluation["trade_count"])

    @property
    def net_pnl_eur(self) -> float:
        return float(self.holdout_evaluation["net_pnl_eur"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHADOW_REVIEW_EVIDENCE_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "holdout_evaluation": dict(self.holdout_evaluation),
            "statistical_gate_summary": dict(self.statistical_gate_summary),
            "fingerprint": self.fingerprint,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
        }


def seal_shadow_review_evidence(
    *,
    experiment_id: str,
    holdout_evaluation: Mapping[str, Any],
    statistical_gate_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a self-checking final-review envelope from already computed evidence."""

    experiment_id = str(experiment_id or "").strip()
    holdout = _mapping(holdout_evaluation, "holdout_evaluation")
    statistical = _mapping(statistical_gate_summary, "statistical_gate_summary")
    return ShadowReviewEvidence(
        experiment_id=experiment_id,
        holdout_evaluation=holdout,
        statistical_gate_summary=statistical,
        fingerprint=_fingerprint(_identity_payload(experiment_id, holdout, statistical)),
    ).to_dict()


def parse_shadow_review_evidence(value: Mapping[str, Any], *, experiment_id: str) -> ShadowReviewEvidence:
    """Parse a serialized envelope and bind it to one registry experiment."""

    payload = _mapping(value, "shadow_review_evidence")
    if int(payload.get("schema_version") or 0) != SHADOW_REVIEW_EVIDENCE_SCHEMA_VERSION:
        raise ShadowReviewEvidenceError("unsupported shadow review evidence schema")
    if str(payload.get("experiment_id") or "").strip() != str(experiment_id or "").strip():
        raise ShadowReviewEvidenceError("shadow review evidence experiment_id does not match")
    return ShadowReviewEvidence(
        experiment_id=str(payload.get("experiment_id") or ""),
        holdout_evaluation=_mapping(payload.get("holdout_evaluation"), "holdout_evaluation"),
        statistical_gate_summary=_mapping(payload.get("statistical_gate_summary"), "statistical_gate_summary"),
        fingerprint=str(payload.get("fingerprint") or ""),
        research_only=payload.get("research_only") is True,
        paper_capital_allowed=payload.get("paper_capital_allowed") is True,
        live_allowed=payload.get("live_allowed") is True,
        promotable=payload.get("promotable") is True,
    )


def _validate_holdout(holdout: Mapping[str, Any], *, experiment_id: str) -> None:
    from .holdout_evaluator import HoldoutEvaluatorError, HoldoutProvenance

    if str(holdout.get("verdict") or "") != HOLDOUT_PASSED_VERDICT:
        raise ShadowReviewEvidenceError("final holdout must pass as research-only evidence")
    if tuple(holdout.get("blockers") or ()):
        raise ShadowReviewEvidenceError("passed final holdout cannot contain blockers")
    _require_research_only(holdout, label="holdout evaluation")
    provenance = _mapping(holdout.get("provenance"), "holdout provenance")
    if str(provenance.get("experiment_id") or "").strip() != experiment_id:
        raise ShadowReviewEvidenceError("holdout provenance experiment_id does not match")
    try:
        HoldoutProvenance(
            **{key: value for key, value in provenance.items() if key != "schema_version"}
        )
    except (HoldoutEvaluatorError, TypeError) as exc:
        raise ShadowReviewEvidenceError(f"holdout provenance is invalid: {exc}") from exc
    if _positive_int(holdout.get("trade_count")) is None:
        raise ShadowReviewEvidenceError("holdout trade_count must be positive")
    if _finite_float(holdout.get("net_pnl_eur")) is None or float(holdout["net_pnl_eur"]) <= 0.0:
        raise ShadowReviewEvidenceError("holdout net_pnl_eur must be positive and finite")


def _validate_statistical_summary(summary: Mapping[str, Any]) -> None:
    if str(summary.get("decision") or "") != STATISTICAL_ELIGIBLE_DECISION:
        raise ShadowReviewEvidenceError("statistical evidence is not eligible for shadow review")
    if tuple(summary.get("blockers") or ()):
        raise ShadowReviewEvidenceError("eligible statistical evidence cannot contain blockers")
    if summary.get("shadow_review_eligible") is not True:
        raise ShadowReviewEvidenceError("statistical evidence must explicitly confirm shadow review eligibility")
    _require_research_only(summary, label="statistical gate summary")
    if _positive_int(summary.get("trade_count")) is None:
        raise ShadowReviewEvidenceError("statistical trade_count must be positive")
    if _positive_int(summary.get("trial_count")) is None:
        raise ShadowReviewEvidenceError("statistical trial_count must be positive")
    if _finite_float(summary.get("net_pnl_eur")) is None or float(summary["net_pnl_eur"]) <= 0.0:
        raise ShadowReviewEvidenceError("statistical net_pnl_eur must be positive and finite")
    if summary.get("net_of_costs") is not True or summary.get("out_of_sample_confirmed") is not True:
        raise ShadowReviewEvidenceError("statistical evidence must confirm costs and out-of-sample validation")


def _validate_overlapping_metrics(holdout: Mapping[str, Any], statistical: Mapping[str, Any]) -> None:
    if int(holdout["trade_count"]) != int(statistical["trade_count"]):
        raise ShadowReviewEvidenceError("holdout and statistical trade_count do not match")
    if not math.isclose(float(holdout["net_pnl_eur"]), float(statistical["net_pnl_eur"]), abs_tol=1e-9):
        raise ShadowReviewEvidenceError("holdout and statistical net_pnl_eur do not match")


def _require_research_only(value: Mapping[str, Any], *, label: str) -> None:
    if value.get("research_only") is not True:
        raise ShadowReviewEvidenceError(f"{label} must be explicitly research-only")
    if any(value.get(key) is True for key in ("paper_capital_allowed", "live_allowed", "promotable")):
        raise ShadowReviewEvidenceError(f"{label} cannot allow paper capital, live or promotion")


def _identity_payload(
    experiment_id: str,
    holdout_evaluation: Mapping[str, Any],
    statistical_gate_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SHADOW_REVIEW_EVIDENCE_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "holdout_evaluation": dict(holdout_evaluation),
        "statistical_gate_summary": dict(statistical_gate_summary),
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ShadowReviewEvidenceError(f"{label} is required")
    return dict(value)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _fingerprint(value: Mapping[str, Any]) -> str:
    return sha256(json.dumps(dict(value), default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
