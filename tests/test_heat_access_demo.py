from __future__ import annotations

import json
from pathlib import Path

import pytest

from civicdecision.connectors.base import write_manifest
from civicdecision.demos.heat_access import (
    HeatAccessDemoConfig,
    build_heat_access_pack,
    render_decision_brief,
    write_decision_artifacts,
)
from civicdecision.errors import AnalysisError
from civicdecision.io import load_document, validate_document
from civicdecision.protocols.base import sha256_bytes
from civicdecision.protocols.decision import DecisionPack, ReversalOutcome, RunStatus
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest

ROOT = Path(__file__).parents[1]
DATA_DIR = ROOT / "examples/data/cdc-places"
DATA = DATA_DIR / "cdc-places-7ccf6e7d6dc3.json"
MANIFEST = DATA_DIR / "cdc-places-7ccf6e7d6dc3.manifest.json"
SCENARIO = ROOT / "examples/scenarios/suffolk-heat-access-demo.yaml"


def test_real_public_sample_compiles_to_completed_decision_pack() -> None:
    pack = build_heat_access_pack(DATA, MANIFEST, SCENARIO)
    assert pack.status is RunStatus.COMPLETED
    assert len(pack.options) == 55
    assert pack.recommendation.selected_option_id == "plan-25025000202-25025000502"
    assert {item.type for item in pack.evidence} == {
        EvidenceType.OBSERVED,
        EvidenceType.ESTIMATED,
        EvidenceType.SIMULATED,
        EvidenceType.OPTIMIZED,
        EvidenceType.PROPOSED,
    }
    assert EvidenceType.CAUSAL not in {item.type for item in pack.evidence}
    assert any(test.outcome is ReversalOutcome.REVERSED for test in pack.reversal_tests)
    assert len(pack.value_of_information) == 3
    assert all("/Users/" not in item for item in pack.reproducibility.command)


def test_decision_artifacts_round_trip_and_use_portable_checksum(tmp_path: Path) -> None:
    pack = build_heat_access_pack(DATA, MANIFEST, SCENARIO)
    artifacts = write_decision_artifacts(pack, tmp_path)
    restored = validate_document(artifacts.pack_path, DecisionPack)
    assert restored.content_hash() == pack.content_hash()
    assert "decision-pack.json" in artifacts.checksum_path.read_text()
    assert "decision-brief.md" in artifacts.checksum_path.read_text()
    assert len(artifacts.checksum_path.read_text().splitlines()) == 2
    assert str(tmp_path) not in artifacts.checksum_path.read_text()
    brief = artifacts.brief_path.read_text()
    assert "Claim boundary" in brief
    assert "not a deployed service" in brief


def test_infeasible_run_is_preserved_and_rendered() -> None:
    pack = build_heat_access_pack(
        DATA,
        MANIFEST,
        SCENARIO,
        HeatAccessDemoConfig(
            max_facilities=1,
            facility_cost=8000,
            budget=8000,
            service_radius_km=0.001,
            minimum_priority_coverage=1,
            sensitivity_radii_km=(0.5,),
        ),
    )
    assert pack.status is RunStatus.INFEASIBLE
    assert pack.recommendation.selected_option_id is None
    assert pack.failure_reason
    assert "Failure reason" in render_decision_brief(pack)


def temporary_sample(tmp_path: Path, payload: object, declared_count: int) -> tuple[Path, Path]:
    content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    data_path = tmp_path / "sample.json"
    data_path.write_bytes(content)
    manifest = validate_document(MANIFEST, SourceManifest)
    manifest.artifact_id = "temporary-sample"
    manifest.artifact_path = data_path.name
    manifest.content_hash = sha256_bytes(content)
    manifest.record_count = declared_count
    manifest_path = tmp_path / "sample.manifest.json"
    write_manifest(manifest_path, manifest)
    return data_path, manifest_path


def test_demo_rejects_manifest_path_mismatch(tmp_path: Path) -> None:
    other = tmp_path / "other.json"
    other.write_text("[]")
    with pytest.raises(AnalysisError, match="does not match"):
        build_heat_access_pack(other, MANIFEST, SCENARIO)


@pytest.mark.parametrize(
    ("payload", "count", "message"),
    [
        ([], 0, "empty"),
        ([{}], 1, "row validation"),
        (load_document(DATA), 11, "record count mismatch"),
    ],
)
def test_demo_rejects_invalid_or_miscounted_samples(
    tmp_path: Path, payload: object, count: int, message: str
) -> None:
    data_path, manifest_path = temporary_sample(tmp_path, payload, count)
    with pytest.raises(AnalysisError, match=message):
        build_heat_access_pack(data_path, manifest_path, SCENARIO)


def test_demo_requires_distinct_sensitivity_radius() -> None:
    with pytest.raises(AnalysisError, match="distinct sensitivity"):
        build_heat_access_pack(
            DATA,
            MANIFEST,
            SCENARIO,
            HeatAccessDemoConfig(sensitivity_radii_km=(1.25,)),
        )
