from __future__ import annotations

import json

import pytest

from autobot.v2 import cli
from autobot.v2.research import public_collector_boundary as boundary
from autobot.v2.research import forward_microstructure_collection as forward_microstructure
from autobot.v2.research import historical_data_collector as historical
from autobot.v2.research import kraken_ohlcvt_archive as ohlcvt_archive
from autobot.v2.research import kraken_futures_derivatives_collector as derivatives
from autobot.v2.research import spread_depth_recorder as spread_depth
from autobot.v2.research import daily_data_collection_runner as daily_runner
from autobot.v2.research.public_collector_boundary import (
    PublicCollectorBoundaryError,
    PublicCollectorBoundaryFinding,
    PublicCollectorBoundaryReport,
    assert_public_collector_boundary,
    audit_public_collector_boundary,
    audit_public_collector_sources,
)


pytestmark = pytest.mark.unit


def test_builtin_public_collectors_have_no_private_credential_or_execution_reference():
    report = audit_public_collector_boundary()

    assert report.passed is True
    assert report.findings == ()
    assert set(report.modules) == set(boundary.PUBLIC_COLLECTOR_MODULES)
    assert report.to_dict()["network_access"] == "not_used"
    assert report.to_dict()["runtime_state_access"] == "not_used"


def test_source_audit_reports_forbidden_private_import_and_reference(tmp_path):
    source = tmp_path / "unsafe_collector.py"
    source.write_text(
        "import krakenex\n"
        "import autobot.v2.order_router.adapters\n"
        "import os\n"
        "from importlib import import_module\n"
        "os.getenv('KRAKEN_API_KEY')\n"
        "import_module('autobot.v2.order_executor_async.adapter')\n"
        "KRAKEN_API_SECRET\n"
        "client.query_private('Balance')\n",
        encoding="utf-8",
    )

    report = audit_public_collector_sources({"unsafe_collector": source})

    assert report.passed is False
    assert {(finding.kind, finding.value) for finding in report.findings} == {
        ("forbidden_import", "krakenex"),
        ("forbidden_import", "autobot.v2.order_router.adapters"),
        ("forbidden_import", "autobot.v2.order_executor_async.adapter"),
        ("forbidden_reference", "KRAKEN_API_KEY"),
        ("forbidden_reference", "KRAKEN_API_SECRET"),
        ("forbidden_reference", "query_private"),
    }


def test_assertion_fails_closed_when_the_audit_has_a_finding(monkeypatch):
    report = PublicCollectorBoundaryReport(
        modules=("historical_data_collector",),
        findings=(
            PublicCollectorBoundaryFinding(
                module="historical_data_collector",
                line=1,
                kind="forbidden_import",
                value="krakenex",
            ),
        ),
    )
    monkeypatch.setattr(boundary, "audit_public_collector_boundary", lambda _modules=None: report)

    with pytest.raises(PublicCollectorBoundaryError, match="public collector boundary violation"):
        assert_public_collector_boundary(("historical_data_collector",))


def test_cli_boundary_audit_is_read_only_and_reports_a_pass(capsys):
    assert cli.main(["audit-public-collector-boundary"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["audit"] == "public_collector_boundary"
    assert payload["passed"] is True
    assert payload["network_access"] == "not_used"
    assert payload["runtime_state_access"] == "not_used"


@pytest.mark.parametrize(
    ("module", "config"),
    [
        (
            historical,
            historical.HistoricalDataCollectorConfig(
                run_id="blocked_historical",
                symbols=("BTCZEUR",),
                output_dir="unused",
            ),
        ),
        (
            spread_depth,
            spread_depth.SpreadDepthRecorderConfig(
                run_id="blocked_depth",
                symbols=("BTCZEUR",),
                output_dir="unused",
            ),
        ),
        (
            forward_microstructure,
            forward_microstructure.ForwardMicrostructureCollectionConfig(
                run_id="blocked_forward",
                symbols=("BTCZEUR",),
                raw_output_dir="unused",
            ),
        ),
        (
            derivatives,
            derivatives.KrakenFuturesCollectorConfig(
                run_id="blocked_derivatives",
                priority_assets=("BTC",),
                raw_dir="unused",
            ),
        ),
    ],
)
def test_public_collector_entrypoints_fail_before_io_when_boundary_audit_fails(
    monkeypatch,
    module,
    config,
):
    def _blocked(_modules):
        raise PublicCollectorBoundaryError("synthetic boundary failure")

    monkeypatch.setattr(module, "assert_public_collector_boundary", _blocked)

    with pytest.raises(PublicCollectorBoundaryError, match="synthetic boundary failure"):
        if module is historical:
            historical.collect_historical_ohlcv(config)
        elif module is spread_depth:
            spread_depth.record_spread_depth(config)
        elif module is forward_microstructure:
            forward_microstructure.collect_forward_microstructure(config)
        else:
            derivatives.collect_kraken_futures_derivatives(config)


def test_archive_import_fails_before_opening_operator_archive_when_boundary_audit_fails(tmp_path, monkeypatch):
    archive = tmp_path / "operator_supplied_archive.zip"
    archive.write_bytes(b"not opened because the boundary must fail first")
    config = ohlcvt_archive.KrakenOhlcvtArchiveImportConfig(
        run_id="blocked_archive",
        archive_path=archive,
        symbols=("BTCZEUR",),
        timeframes=("5m",),
        raw_dir=tmp_path / "raw",
        normalized_dir=tmp_path / "normalized",
        manifest_dir=tmp_path / "manifests",
        report_dir=tmp_path / "reports",
    )

    monkeypatch.setattr(
        ohlcvt_archive,
        "assert_public_collector_boundary",
        lambda _modules: (_ for _ in ()).throw(PublicCollectorBoundaryError("synthetic boundary failure")),
    )

    with pytest.raises(PublicCollectorBoundaryError, match="synthetic boundary failure"):
        ohlcvt_archive.import_kraken_ohlcvt_archive(config)


def test_daily_runner_fails_before_reading_config_when_boundary_audit_fails(monkeypatch):
    monkeypatch.setattr(
        daily_runner,
        "assert_public_collector_boundary",
        lambda _modules: (_ for _ in ()).throw(PublicCollectorBoundaryError("synthetic boundary failure")),
    )

    with pytest.raises(PublicCollectorBoundaryError, match="synthetic boundary failure"):
        daily_runner.run_daily_research_data_collection(
            config_path="must_not_be_opened.yaml",
            run_id="blocked_daily_runner",
        )
