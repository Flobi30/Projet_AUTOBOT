from __future__ import annotations

from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.forward_microstructure_collection import (
    ForwardMicrostructureCollectionConfig,
    collect_forward_microstructure,
)


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR", "base": "XXBT", "quote": "ZEUR"},
        "ETHZEUR": {"altname": "ETHEUR", "wsname": "ETH/EUR", "base": "XETH", "quote": "ZEUR"},
    }


def _depth_fetcher(pair: str, depth_count: int):
    return {
        "error": [],
        "result": {
            pair: {
                "bids": [["100.0", "4.0", "1780272000"]],
                "asks": [["100.2", "5.0", "1780272001"]],
            }
        },
    }


def test_forward_microstructure_collection_is_bounded_canonical_and_non_executable(tmp_path):
    result = collect_forward_microstructure(
        ForwardMicrostructureCollectionConfig(
            run_id="pytest_forward_microstructure",
            symbols=("BTCZEUR", "ETHZEUR"),
            raw_output_dir=tmp_path / "raw",
            canonical_output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
            depth_count=5,
            samples=1,
            max_runtime_seconds=60,
        ),
        fetcher=_depth_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert result.status == "ok"
    assert len(result.recorder.snapshots) == 2
    assert result.canonical_snapshot is not None
    assert result.canonical_snapshot.canonical_row_count == 2
    assert result.canonical_snapshot.runtime_parity_proven is False
    assert result.canonical_snapshot.execution_eligible is False
    assert Path(str(result.manifest_path)).exists()
    assert Path(str(result.markdown_report_path)).exists()


def test_forward_microstructure_cli_requires_explicit_symbols_and_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect-microstructure-forward",
            "--run-id",
            "pytest_cli",
            "--symbols",
            "BTCZEUR,ETHZEUR",
            "--samples",
            "1",
        ]
    )

    assert args.command == "collect-microstructure-forward"
    assert args.symbols == "BTCZEUR,ETHZEUR"
    assert args.samples == 1

    with pytest.raises(SystemExit):
        parser.parse_args(["collect-microstructure-forward", "--run-id", "missing_symbols"])
