"""Immutable research cost evidence derived from canonical microstructure profiles.

Canonical top-of-book profiles describe observed public REST conditions.  This
module makes that description auditable when a researcher elects to use it for
one cost model: the selected model can only become *more* conservative than
its original fallback spread, and the resulting evidence remains research
only.  It does not contact an exchange, alter a global cost profile, create an
order, or prove runtime-feed parity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from autobot.v2.contracts import AlphaSignal, MarketIdentity

from .backtest_alpha_adapter import cost_model_fingerprint
from .canonical_microstructure_profile import (
    CanonicalMicrostructureProfileReport,
    CanonicalMicrostructureSymbolProfile,
)
from .execution_cost_model import ExecutionCostConfig


MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION = 1


class MicrostructureCostEvidenceError(ValueError):
    """Raised when descriptive microstructure evidence is used inconsistently."""


def _sha256_text(value: object, field_name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise MicrostructureCostEvidenceError(f"{field_name} must be a SHA-256 hex digest")
    return text


def _finite_non_negative(value: object, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise MicrostructureCostEvidenceError(f"{field_name} must be finite and non-negative")
    return number


@dataclass(frozen=True)
class MicrostructureCostEvidence:
    """A non-authorizing link between one market profile and one cost model.

    ``central_cost_config`` uses the larger of the supplied fallback spread and
    the profile's observed research spread.  ``stress_cost_config`` similarly
    incorporates the observed stress spread.  Neither config is installed
    globally or used unless an explicit research caller supplies it.
    """

    schema_version: int
    evidence_id: str
    evidence_fingerprint: str
    generated_at: str
    market: MarketIdentity
    profile_run_id: str
    profile_source_fingerprint: str
    profile_status: str
    calibration_status: str
    observed_research_spread_bps: float
    observed_stress_spread_bps: float
    median_bid_depth_eur: float
    median_ask_depth_eur: float
    p95_latency_ms: float
    central_cost_config: ExecutionCostConfig
    stress_cost_config: ExecutionCostConfig
    central_cost_model_fingerprint: str
    stress_cost_model_fingerprint: str
    research_only: bool = True
    runtime_parity_proven: bool = False
    execution_eligible: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION:
            raise MicrostructureCostEvidenceError("unsupported microstructure cost evidence schema")
        if not isinstance(self.market, MarketIdentity):
            raise MicrostructureCostEvidenceError("market must be a MarketIdentity")
        if self.market.exchange != "kraken" or self.market.market_type != "spot" or self.market.quote_asset != "EUR":
            raise MicrostructureCostEvidenceError("microstructure cost evidence requires explicit Kraken spot EUR market")
        for field_name in ("evidence_id", "profile_run_id", "profile_status", "calibration_status"):
            if not str(getattr(self, field_name)).strip():
                raise MicrostructureCostEvidenceError(f"{field_name} is required")
        evidence_fingerprint = _sha256_text(self.evidence_fingerprint, "evidence_fingerprint")
        expected_evidence_id = (
            f"microstructure_cost_v{MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION}_{evidence_fingerprint[:16]}"
        )
        if self.evidence_id != expected_evidence_id:
            raise MicrostructureCostEvidenceError("evidence_id does not match evidence_fingerprint")
        source_fingerprint = _sha256_text(self.profile_source_fingerprint, "profile_source_fingerprint")
        central_fingerprint = _sha256_text(self.central_cost_model_fingerprint, "central_cost_model_fingerprint")
        stress_fingerprint = _sha256_text(self.stress_cost_model_fingerprint, "stress_cost_model_fingerprint")
        for field_name in (
            "observed_research_spread_bps",
            "observed_stress_spread_bps",
            "median_bid_depth_eur",
            "median_ask_depth_eur",
            "p95_latency_ms",
        ):
            object.__setattr__(self, field_name, _finite_non_negative(getattr(self, field_name), field_name))
        if self.observed_stress_spread_bps < self.observed_research_spread_bps:
            raise MicrostructureCostEvidenceError("observed_stress_spread_bps cannot be below observed_research_spread_bps")
        if not isinstance(self.central_cost_config, ExecutionCostConfig) or not isinstance(self.stress_cost_config, ExecutionCostConfig):
            raise MicrostructureCostEvidenceError("cost evidence requires ExecutionCostConfig values")
        self.central_cost_config.validate()
        self.stress_cost_config.validate()
        if self.central_cost_config.fallback_spread_bps + 1e-12 < self.observed_research_spread_bps:
            raise MicrostructureCostEvidenceError("central_cost_config_understates_observed_research_spread")
        if self.stress_cost_config.fallback_spread_bps + 1e-12 < self.observed_stress_spread_bps:
            raise MicrostructureCostEvidenceError("stress_cost_config_understates_observed_stress_spread")
        if cost_model_fingerprint(self.central_cost_config.to_dict()) != central_fingerprint:
            raise MicrostructureCostEvidenceError("central_cost_model_fingerprint_mismatch")
        if cost_model_fingerprint(self.stress_cost_config.to_dict()) != stress_fingerprint:
            raise MicrostructureCostEvidenceError("stress_cost_model_fingerprint_mismatch")
        if self.profile_status != "RESEARCH_CALIBRATION_READY" or self.calibration_status != "RESEARCH_CALIBRATION_READY":
            raise MicrostructureCostEvidenceError("microstructure_profile_not_research_calibration_ready")
        if self.runtime_parity_proven or self.execution_eligible or self.paper_capital_allowed or self.live_allowed or not self.research_only:
            raise MicrostructureCostEvidenceError("microstructure cost evidence is research-only and non-authorizing")
        object.__setattr__(self, "evidence_fingerprint", evidence_fingerprint)
        object.__setattr__(self, "profile_source_fingerprint", source_fingerprint)
        object.__setattr__(self, "central_cost_model_fingerprint", central_fingerprint)
        object.__setattr__(self, "stress_cost_model_fingerprint", stress_fingerprint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "evidence_fingerprint": self.evidence_fingerprint,
            "generated_at": self.generated_at,
            "market": asdict(self.market),
            "profile_run_id": self.profile_run_id,
            "profile_source_fingerprint": self.profile_source_fingerprint,
            "profile_status": self.profile_status,
            "calibration_status": self.calibration_status,
            "observed_research_spread_bps": self.observed_research_spread_bps,
            "observed_stress_spread_bps": self.observed_stress_spread_bps,
            "median_bid_depth_eur": self.median_bid_depth_eur,
            "median_ask_depth_eur": self.median_ask_depth_eur,
            "p95_latency_ms": self.p95_latency_ms,
            "central_cost_config": self.central_cost_config.to_dict(),
            "stress_cost_config": self.stress_cost_config.to_dict(),
            "central_cost_model_fingerprint": self.central_cost_model_fingerprint,
            "stress_cost_model_fingerprint": self.stress_cost_model_fingerprint,
            "research_only": self.research_only,
            "runtime_parity_proven": self.runtime_parity_proven,
            "execution_eligible": self.execution_eligible,
            "paper_capital_allowed": self.paper_capital_allowed,
            "live_allowed": self.live_allowed,
        }

    def validation_reason_for_signal(
        self,
        signal: AlphaSignal,
        *,
        base_cost_config: ExecutionCostConfig,
    ) -> str | None:
        """Return a fail-closed reason if a signal is not bound to this evidence."""

        if signal.market != self.market:
            return "microstructure_cost_market_identity_mismatch"
        if cost_model_fingerprint(base_cost_config.to_dict()) != self.central_cost_model_fingerprint:
            return "microstructure_cost_model_fingerprint_mismatch"
        declared = str(signal.metadata.get("microstructure_cost_evidence_fingerprint") or "").strip().lower()
        if not declared:
            return "microstructure_cost_evidence_fingerprint_missing"
        if declared != self.evidence_fingerprint:
            return "microstructure_cost_evidence_fingerprint_mismatch"
        return None


def derive_microstructure_cost_evidence(
    report: CanonicalMicrostructureProfileReport,
    *,
    market: MarketIdentity,
    base_cost_config: ExecutionCostConfig,
    generated_at: datetime | None = None,
) -> MicrostructureCostEvidence:
    """Create conservative, explicit research evidence for one exact market.

    The caller owns the returned configuration.  This function never writes a
    profile, changes defaults, or causes a strategy to use the evidence.
    """

    if not isinstance(report, CanonicalMicrostructureProfileReport):
        raise MicrostructureCostEvidenceError("report must be CanonicalMicrostructureProfileReport")
    if report.status != "RESEARCH_CALIBRATION_READY":
        raise MicrostructureCostEvidenceError("microstructure_profile_not_research_calibration_ready")
    if market.exchange != "kraken" or market.market_type != "spot" or market.quote_asset != "EUR":
        raise MicrostructureCostEvidenceError("microstructure cost evidence requires explicit Kraken spot EUR market")
    profile = _profile_for_market(report, market)
    if profile.calibration_status != "RESEARCH_CALIBRATION_READY":
        raise MicrostructureCostEvidenceError("microstructure_symbol_not_research_calibration_ready")
    base_cost_config.validate()
    research_spread = _finite_non_negative(profile.observed_research_spread_bps, "observed_research_spread_bps")
    stress_spread = _finite_non_negative(profile.observed_stress_spread_bps, "observed_stress_spread_bps")
    if stress_spread < research_spread:
        raise MicrostructureCostEvidenceError("observed_stress_spread_bps cannot be below observed_research_spread_bps")
    central_cost_config = replace(
        base_cost_config,
        fallback_spread_bps=max(float(base_cost_config.fallback_spread_bps), research_spread),
        runtime_comparable=False,
    )
    stress_cost_config = replace(
        central_cost_config,
        fallback_spread_bps=max(float(central_cost_config.fallback_spread_bps), stress_spread),
    )
    central_cost_config.validate()
    stress_cost_config.validate()
    central_fingerprint = cost_model_fingerprint(central_cost_config.to_dict())
    stress_fingerprint = cost_model_fingerprint(stress_cost_config.to_dict())
    generated = (generated_at or datetime.now(timezone.utc))
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise MicrostructureCostEvidenceError("generated_at must be timezone-aware")
    generated = generated.astimezone(timezone.utc)
    payload = {
        "schema_version": MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION,
        "market": asdict(market),
        "profile_run_id": report.run_id,
        "profile_source_fingerprint": report.source_fingerprint,
        "profile_status": report.status,
        "calibration_status": profile.calibration_status,
        "observed_research_spread_bps": research_spread,
        "observed_stress_spread_bps": stress_spread,
        "median_bid_depth_eur": profile.median_bid_depth_eur,
        "median_ask_depth_eur": profile.median_ask_depth_eur,
        "p95_latency_ms": profile.p95_latency_ms,
        "central_cost_model_fingerprint": central_fingerprint,
        "stress_cost_model_fingerprint": stress_fingerprint,
    }
    fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return MicrostructureCostEvidence(
        schema_version=MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION,
        evidence_id=f"microstructure_cost_v{MICROSTRUCTURE_COST_EVIDENCE_SCHEMA_VERSION}_{fingerprint[:16]}",
        evidence_fingerprint=fingerprint,
        generated_at=generated.isoformat(),
        market=market,
        profile_run_id=report.run_id,
        profile_source_fingerprint=report.source_fingerprint,
        profile_status=report.status,
        calibration_status=profile.calibration_status,
        observed_research_spread_bps=research_spread,
        observed_stress_spread_bps=stress_spread,
        median_bid_depth_eur=profile.median_bid_depth_eur,
        median_ask_depth_eur=profile.median_ask_depth_eur,
        p95_latency_ms=profile.p95_latency_ms,
        central_cost_config=central_cost_config,
        stress_cost_config=stress_cost_config,
        central_cost_model_fingerprint=central_fingerprint,
        stress_cost_model_fingerprint=stress_fingerprint,
    )


def render_microstructure_cost_evidence(evidence: MicrostructureCostEvidence) -> str:
    """Render a compact decision record without implying an execution permit."""

    return "\n".join(
        (
            f"# Microstructure Cost Evidence - {evidence.evidence_id}",
            "",
            f"Market: `{evidence.market.exchange}/{evidence.market.market_type}/{evidence.market.symbol}`",
            f"Evidence fingerprint: `{evidence.evidence_fingerprint}`",
            f"Profile source fingerprint: `{evidence.profile_source_fingerprint}`",
            f"Calibration: `{evidence.calibration_status}`",
            f"Observed research / stress spread bps: `{evidence.observed_research_spread_bps:.6f}` / `{evidence.observed_stress_spread_bps:.6f}`",
            f"Central / stress cost-model fingerprint: `{evidence.central_cost_model_fingerprint}` / `{evidence.stress_cost_model_fingerprint}`",
            "",
            "## Boundary",
            "",
            "- Read-only research calibration evidence; it does not update global cost profiles.",
            "- It can only raise a supplied fallback spread, never lower it.",
            "- It does not prove runtime-feed parity and does not authorize shadow, paper, live, capital, promotion, or an order.",
            "",
        )
    )


def write_microstructure_cost_evidence(
    evidence: MicrostructureCostEvidence,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write compact research artifacts; source profile data stays unchanged."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"{evidence.evidence_id}.json"
    markdown_path = destination / f"{evidence.evidence_id}.md"
    json_path.write_text(json.dumps(evidence.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_microstructure_cost_evidence(evidence), encoding="utf-8")
    return json_path, markdown_path


def _profile_for_market(
    report: CanonicalMicrostructureProfileReport,
    market: MarketIdentity,
) -> CanonicalMicrostructureSymbolProfile:
    candidates = [
        profile
        for profile in report.profiles
        if profile.symbol == market.symbol
        and profile.base_asset == market.base_asset
        and profile.quote_asset == market.quote_asset
    ]
    if not candidates:
        raise MicrostructureCostEvidenceError("microstructure_profile_market_missing")
    if len(candidates) != 1:
        raise MicrostructureCostEvidenceError("microstructure_profile_market_ambiguous")
    return candidates[0]
