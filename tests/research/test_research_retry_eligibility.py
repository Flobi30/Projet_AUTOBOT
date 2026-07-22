import ast
import json
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.research.data_capability_scanner import DataCapability
from autobot.v2.research.research_memory_store import ResearchMemoryStore
from autobot.v2.research.research_retry_eligibility import (
    assess_research_retry_eligibility,
    build_material_data_signature,
    load_research_memory_records,
    write_research_retry_eligibility_report,
)


pytestmark = pytest.mark.unit


def _capabilities(*, funding=True, basis=True, open_interest=True, source_root: str = "one"):
    return (
        DataCapability(
            capability_id="funding_rates",
            available=funding,
            source_paths=(f"/{source_root}/funding.csv",),
            provider="kraken_futures_public",
            symbols=("PF_XBTUSD",),
            start_at="2025-07-01T00:00:00+00:00",
            end_at="2026-07-22T00:00:00+00:00",
            row_count=50000,
            quality_status="historical_funding_ready" if funding else "missing",
            blockers=() if funding else ("funding_rates_missing",),
        ),
        DataCapability(
            capability_id="spot_perp_basis",
            available=basis,
            source_paths=(f"/{source_root}/basis.csv",),
            provider="kraken_futures_public",
            symbols=("PF_XBTUSD",),
            start_at="2026-07-17T00:00:00+00:00",
            end_at="2026-07-22T00:00:00+00:00",
            row_count=58000,
            quality_status="basis_history_ready" if basis else "current_basis_only_waiting_for_history",
            proxy_status="not_proxy",
            blockers=() if basis else ("basis_history_too_short",),
        ),
        DataCapability(
            capability_id="open_interest",
            available=open_interest,
            source_paths=(f"/{source_root}/oi.csv",),
            provider="kraken_futures_public",
            symbols=("PF_XBTUSD",),
            start_at="2026-07-17T00:00:00+00:00",
            end_at="2026-07-22T00:00:00+00:00",
            row_count=53000,
            quality_status="open_interest_history_ready" if open_interest else "current_open_interest_only",
            blockers=() if open_interest else ("open_interest_history_missing",),
        ),
    )


def _record(
    run_id: str,
    status: str,
    *,
    reasons=(),
    blockers=(),
    variants: int = 1,
):
    return {
        "run_id": run_id,
        "hypothesis_id": "funding_basis",
        "alpha_family_id": "funding_basis",
        "template_id": "funding_extreme_reversion",
        "created_at": "2026-07-22T00:00:00+00:00",
        "data_snapshot": {},
        "parameters_tested": {},
        "symbols_tested": [],
        "gate_results": [],
        "final_status": status,
        "rejection_reasons": list(reasons),
        "variant_count": variants,
        "trial_count_for_family": variants,
        "trial_count_for_template": variants,
        "related_rejected_hypotheses": [],
        "do_not_rerun_until": None,
        "requires_new_data_before_rerun": False,
        "metrics": {"blockers": list(blockers)},
        "paper_capital_allowed": False,
        "live_allowed": False,
        "promotable": False,
    }


def test_signature_excludes_host_specific_paths_and_freshness():
    first = build_material_data_signature(hypothesis_id="funding_basis", capabilities=_capabilities(source_root="laptop"))
    second = build_material_data_signature(hypothesis_id="funding_basis", capabilities=_capabilities(source_root="vps"))

    assert first.fingerprint == second.fingerprint


def test_insufficient_data_with_ready_basis_is_only_eligible_as_new_named_research_campaign():
    record = _record(
        "old_waiting",
        "INSUFFICIENT_DATA",
        reasons=("derivatives_waiting_for_more_data",),
        blockers=("BASIS_HISTORY_WAITING", "OPEN_INTEREST_HISTORY_WAITING"),
        variants=2,
    )

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=(record,),
        research_campaign_id="funding-basis-canonical-derivatives-v1",
    )

    assert report.status == "NEW_CAMPAIGN_ELIGIBLE_RESEARCH_ONLY"
    assert report.material_capability_gains == ("spot_perp_basis", "open_interest")
    assert report.predecessor_trial_count_floor == 2
    assert report.new_campaign_registration_allowed is True
    assert report.scheduler_rerun_allowed is False
    assert report.runner_execution_allowed is False
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.order_created is False


def test_material_change_never_runs_without_an_explicit_campaign_id():
    record = _record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",))

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=(record,),
    )

    assert report.status == "MATERIAL_CHANGE_DETECTED_NEW_CAMPAIGN_REQUIRED"
    assert report.new_campaign_registration_allowed is False


def test_performance_rejection_stays_blocked_despite_new_derivatives_data():
    record = _record(
        "negative_edge",
        "REJECT_FAST",
        reasons=("profit_factor_net_not_above_1", "sample_size_below_template_minimum"),
        blockers=("BASIS_HISTORY_WAITING",),
    )

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=(record,),
        research_campaign_id="attempted-bypass",
    )

    assert report.status == "BLOCKED_PRIOR_PERFORMANCE_REJECTION"
    assert report.new_campaign_registration_allowed is False


def test_selected_old_data_waiting_record_cannot_bypass_later_performance_rejection():
    old_waiting = _record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",), variants=2)
    later_negative = _record("later_negative", "REJECT_FAST", reasons=("edge_net_not_positive",), variants=3)

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=(old_waiting, later_negative),
        prior_run_id="old_waiting",
        research_campaign_id="attempted-bypass",
    )

    assert report.status == "BLOCKED_LATER_PERFORMANCE_REJECTION"
    assert report.latest_terminal_run_id == "later_negative"
    assert report.predecessor_trial_count_floor == 5


def test_current_required_basis_data_must_be_ready_before_any_campaign_is_considered():
    record = _record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",))

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(basis=False),
        memory_records=(record,),
        research_campaign_id="not-ready",
    )

    assert report.status == "BLOCKED_CURRENT_REQUIRED_DATA_MISSING"


def test_assessment_reads_sqlite_memory_without_writing_or_erasing_records(tmp_path):
    memory_path = tmp_path / "memory.sqlite3"
    store = ResearchMemoryStore(memory_path)
    store.append(_record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",)))
    before = store.event_count()

    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=load_research_memory_records(memory_path),
    )

    assert report.status == "MATERIAL_CHANGE_DETECTED_NEW_CAMPAIGN_REQUIRED"
    assert store.event_count() == before


def test_report_writer_is_a_compact_audit_output(tmp_path):
    report = assess_research_retry_eligibility(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        capabilities=_capabilities(),
        memory_records=(_record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",)),),
    )
    json_path, markdown_path = write_research_retry_eligibility_report(report, tmp_path, run_id="retry fixture")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert markdown_path.exists()
    assert payload["scheduler_rerun_allowed"] is False
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["order_created"] is False


def test_cli_assessment_is_read_only_and_never_enables_execution(tmp_path, capsys):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "pytest_kraken_futures_derivatives.json").write_text(
        json.dumps(
            {
                "snapshot_id": "derivatives-canonical",
                "fingerprint": "derivatives-fingerprint",
                "mappings": [{"futures_symbol": "PF_XBTUSD", "base_asset": "BTC"}],
                "funding_history_ready": True,
                "funding_history_row_count": 50_000,
                "basis_current_ready": True,
                "basis_history_ready": True,
                "basis_history_row_count": 58_000,
                "current_open_interest_ready": True,
                "open_interest_history_ready": True,
                "open_interest_history_row_count": 53_000,
                "derivatives_data_quality": "historical_funding_and_same_quote_basis_ready_research_only",
                "datasets": [],
            }
        ),
        encoding="utf-8",
    )
    memory_path = tmp_path / "memory.sqlite3"
    ResearchMemoryStore(memory_path).append(
        _record("old_waiting", "INSUFFICIENT_DATA", blockers=("BASIS_HISTORY_WAITING",))
    )

    exit_code = cli.main(
        [
            "research-retry-eligibility",
            "--hypothesis-id",
            "funding_basis",
            "--template-id",
            "funding_extreme_reversion",
            "--data-roots",
            str(manifest_dir),
            "--memory-path",
            str(memory_path),
            "--no-write-report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "MATERIAL_CHANGE_DETECTED_NEW_CAMPAIGN_REQUIRED"
    assert payload["scheduler_rerun_allowed"] is False
    assert payload["runner_execution_allowed"] is False
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["report_paths"] is None


def test_materiality_gate_has_no_runtime_or_execution_imports():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/research_retry_eligibility.py").read_text(encoding="utf-8"))
    forbidden = {
        "autobot.v2.signal_handler_async",
        "autobot.v2.order_router",
        "autobot.v2.paper_trading",
        "autobot.v2.order_executor",
        "autobot.v2.orchestrator_async",
        "autobot.v2.research.bounded_research_coordinator",
    }
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
