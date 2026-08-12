from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from civicdecision.errors import AnalysisError
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.standardized import build as tier_s_build
from civicdecision.standardized.build import (
    build_tier_s_registry,
    write_tier_s_artifacts,
)
from civicdecision.standardized.models import (
    DataQualityReport,
    DecisionReadiness,
    GeographicAlignment,
    QualityStatus,
    ScenarioScreenStatus,
    StandardizedCityBundle,
    StandardMetric,
    StandardScenarioRun,
    TierSRegistry,
)

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "catalog/global-cities/cities-tier-g.json"
CLIMATE = ROOT / "examples/data/tier-s/nasa-power"
CONTEXT = ROOT / "examples/data/tier-s/world-bank"
OUTPUT = ROOT / "catalog/standardized-cities"


def test_committed_tier_s_registry_has_30_cities_and_90_runs() -> None:
    registry = TierSRegistry.model_validate_json((OUTPUT / "registry.json").read_bytes())
    assert registry.target_count == 30
    assert len(registry.entries) == 30
    assert sum(len(item.run_refs) for item in registry.entries) == 90
    statuses = [status for item in registry.entries for status in item.scenario_statuses]
    assert statuses.count(ScenarioScreenStatus.SCREENED) == 60
    assert statuses.count(ScenarioScreenStatus.INSUFFICIENT_EVIDENCE) == 30
    assert all(item.quality_status is QualityStatus.PASS for item in registry.entries)
    assert registry.entries[0].name == "Shanghai"
    assert registry.entries[-1].name == "Jeddah"
    assert registry.entries[-1].tier_g_rank == 31
    assert len(registry.exclusions_before_target) == 1
    exclusion = registry.exclusions_before_target[0]
    assert exclusion.name == "Taipei"
    assert exclusion.tier_g_rank == 19
    assert any("World Bank" in reason for reason in exclusion.reasons)


def test_cross_city_report_covers_every_city_without_recommendations() -> None:
    rows = (OUTPUT / "cross-city-comparison.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 31
    assert "recommendations_issued" in rows[0]
    assert all(row.endswith(",0") for row in rows[1:])
    report = (OUTPUT / "cross-city-comparison.md").read_text(encoding="utf-8")
    assert "composite score" in report
    assert "Taipei" in report
    assert report.count("| 30 | Jeddah |") == 2


def test_committed_tier_s_bundles_preserve_scope_boundaries() -> None:
    paths = sorted((OUTPUT / "cities").glob("*/bundle.json"))
    assert len(paths) == 30
    for path in paths:
        bundle = StandardizedCityBundle.model_validate_json(path.read_bytes())
        assert bundle.quality_report.completeness_rate == 1
        assert bundle.quality_report.missing_values == 0
        assert len(bundle.source_manifests) == 5
        assert len(bundle.metrics) == 11
        assert len(bundle.scenario_runs) == 3
        alignments = {item.alignment for item in bundle.source_bindings}
        assert alignments == {
            GeographicAlignment.IDENTITY_POINT,
            GeographicAlignment.GRIDDED_POINT,
            GeographicAlignment.COUNTRY_CONTEXT,
        }
        assert all(metric.evidence_type is EvidenceType.ESTIMATED for metric in bundle.metrics)
        assert all(not run.recommendation_issued for run in bundle.scenario_runs)


def test_committed_tier_s_independent_run_files_match_bundle_hashes() -> None:
    registry = TierSRegistry.model_validate_json((OUTPUT / "registry.json").read_bytes())
    for entry in registry.entries:
        bundle = StandardizedCityBundle.model_validate_json(
            (OUTPUT / entry.bundle_ref).read_bytes()
        )
        assert bundle.content_hash() == entry.bundle_hash
        for index, run_ref in enumerate(entry.run_refs):
            run = StandardScenarioRun.model_validate_json((OUTPUT / run_ref).read_bytes())
            assert run == bundle.scenario_runs[index]
            assert run.content_hash() == entry.run_hashes[index]


def test_tier_s_build_is_byte_deterministic(tmp_path: Path) -> None:
    registry, bundles = build_tier_s_registry(CATALOG, CLIMATE, CONTEXT, target_count=3)
    first = write_tier_s_artifacts(registry, bundles, tmp_path / "first")
    second = write_tier_s_artifacts(registry, bundles, tmp_path / "second")
    first_files = sorted(
        path.relative_to(tmp_path / "first") for path in (tmp_path / "first").rglob("*")
    )
    second_files = sorted(
        path.relative_to(tmp_path / "second") for path in (tmp_path / "second").rglob("*")
    )
    assert first_files == second_files
    for relative in first_files:
        if (tmp_path / "first" / relative).is_file():
            assert (tmp_path / "first" / relative).read_bytes() == (
                tmp_path / "second" / relative
            ).read_bytes()
    assert len(first.bundle_paths) == 3
    assert len(first.run_paths) == 9
    assert first.checksum_path.read_bytes() == second.checksum_path.read_bytes()


def test_tier_s_build_requires_complete_eligible_city_set(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="only 30 cities"):
        build_tier_s_registry(CATALOG, CLIMATE, CONTEXT, target_count=31)

    manifest = next(CONTEXT.glob("*.manifest.json"))
    partial = tmp_path / "context"
    partial.mkdir()
    payload = json.loads(manifest.read_text())
    artifact = CONTEXT / payload["artifact_path"]
    (partial / manifest.name).write_bytes(manifest.read_bytes())
    (partial / artifact.name).write_bytes(artifact.read_bytes())
    with pytest.raises(AnalysisError, match="exactly three indicators"):
        build_tier_s_registry(CATALOG, CLIMATE, partial, target_count=1)


def test_standard_scenario_run_rejects_claim_upgrade() -> None:
    path = next((OUTPUT / "runs").glob("*.json"))
    payload = json.loads(path.read_text())
    payload["recommendation_issued"] = True
    with pytest.raises(ValidationError, match="False"):
        StandardScenarioRun.model_validate(payload)

    payload = json.loads(path.read_text())
    payload["analysis_mode"] = "optimization"
    with pytest.raises(ValidationError, match="descriptive"):
        StandardScenarioRun.model_validate(payload)


def test_standard_scenario_status_and_readiness_must_align() -> None:
    path = next((OUTPUT / "runs").glob("*heat*.json"))
    payload = json.loads(path.read_text())
    payload["decision_readiness"] = DecisionReadiness.INSUFFICIENT_EVIDENCE.value
    with pytest.raises(ValidationError, match="descriptive-only"):
        StandardScenarioRun.model_validate(payload)


def test_tier_s_bundle_rejects_country_context_as_point_alignment() -> None:
    path = next((OUTPUT / "cities").glob("*/bundle.json"))
    payload = json.loads(path.read_text())
    for binding in payload["source_bindings"]:
        if binding["alignment"] == "country-context":
            binding["alignment"] = "gridded-point"
    with pytest.raises(ValidationError, match="required geographic alignment"):
        StandardizedCityBundle.model_validate(payload)


def test_tier_s_bundle_rejects_failed_quality_or_incomplete_values() -> None:
    path = next((OUTPUT / "cities").glob("*/bundle.json"))
    payload = json.loads(path.read_text())
    payload["quality_report"]["checks"][0]["status"] = "fail"
    payload["quality_report"]["overall_status"] = "fail"
    with pytest.raises(ValidationError, match="failed required quality"):
        StandardizedCityBundle.model_validate(payload)

    payload = json.loads(path.read_text())
    payload["quality_report"]["completeness_rate"] = 0.99
    with pytest.raises(ValidationError, match="must be complete"):
        StandardizedCityBundle.model_validate(payload)


def test_quality_report_rejects_duplicate_checks_and_status_mismatch() -> None:
    bundle = json.loads(next((OUTPUT / "cities").glob("*/bundle.json")).read_text())
    payload = json.loads(next((OUTPUT / "cities").glob("*/bundle.json")).read_text())[
        "quality_report"
    ]
    payload["checks"].append(payload["checks"][0])
    with pytest.raises(ValidationError, match="check ids must be unique"):
        DataQualityReport.model_validate(payload)

    payload = bundle["quality_report"]
    payload["overall_status"] = "warn"
    with pytest.raises(ValidationError, match="does not match"):
        DataQualityReport.model_validate(payload)

    payload["checks"][0]["status"] = "warn"
    report = DataQualityReport.model_validate(payload)
    assert report.overall_status is QualityStatus.WARN


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate-source", "source references must be unique"),
        ("unsupported-evidence", "observed or estimated"),
        ("missing-method", "require a method"),
    ],
)
def test_standard_metric_evidence_and_lineage_gates(case: str, message: str) -> None:
    bundle = json.loads(next((OUTPUT / "cities").glob("*/bundle.json")).read_text())
    payload = bundle["metrics"][0]
    if case == "duplicate-source":
        payload["source_refs"] *= 2
    elif case == "unsupported-evidence":
        payload["evidence_type"] = "causal"
    else:
        payload["method"] = None
    with pytest.raises(ValidationError, match=message):
        StandardMetric.model_validate(payload)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate-source", "source references must be unique"),
        ("duplicate-metric", "metric ids must be unique"),
        ("unknown-metric-source", "metric source is not declared"),
        ("negative-readiness", "negative screening runs"),
    ],
)
def test_standard_scenario_internal_gates(case: str, message: str) -> None:
    path = next((OUTPUT / "runs").glob("*policy-readiness*.json"))
    payload = json.loads(path.read_text())
    if case == "duplicate-source":
        payload["source_refs"] *= 2
    elif case == "duplicate-metric":
        payload["metrics"].append(payload["metrics"][0])
    elif case == "unknown-metric-source":
        payload["metrics"][0]["source_refs"] = ["unknown-source"]
    else:
        payload["decision_readiness"] = "descriptive-only"
    with pytest.raises(ValidationError, match=message):
        StandardScenarioRun.model_validate(payload)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("wrong-tier", "Tier-S adapter"),
        ("city-mismatch", "city identifiers must match"),
        ("duplicate-manifest", "manifest artifact identifiers must be unique"),
        ("duplicate-binding", "binding artifact identifiers must be unique"),
        ("binding-set", "cover every source manifest"),
        ("binding-content", "does not match its source manifest"),
        ("adapter-sources", "source ids must match"),
        ("duplicate-metric", "bundle metric ids must be unique"),
        ("unknown-metric-source", "bundle metric source is not declared"),
        ("duplicate-run", "run identifiers must be unique"),
        ("duplicate-template", "templates must be non-duplicative"),
        ("run-city", "run city does not match"),
        ("undeclared-run-metric", "undeclared bundle metric"),
    ],
)
def test_standardized_bundle_cross_object_invariants(case: str, message: str) -> None:
    payload = json.loads(next((OUTPUT / "cities").glob("*/bundle.json")).read_text())
    if case == "wrong-tier":
        payload["adapter"]["tier"] = "G"
    elif case == "city-mismatch":
        payload["adapter"]["city_id"] = "changed.city"
    elif case == "duplicate-manifest":
        payload["source_manifests"][-1] = payload["source_manifests"][0]
    elif case == "duplicate-binding":
        payload["source_bindings"][-1] = payload["source_bindings"][0]
    elif case == "binding-set":
        payload["source_bindings"].pop()
    elif case == "binding-content":
        payload["source_bindings"][0]["source_id"] = "changed-source"
    elif case == "adapter-sources":
        payload["adapter"]["source_ids"].append("changed-source")
    elif case == "duplicate-metric":
        payload["metrics"].append(payload["metrics"][0])
    elif case == "unknown-metric-source":
        payload["metrics"][0]["source_refs"] = ["changed-source"]
    elif case == "duplicate-run":
        payload["scenario_runs"][1]["run_id"] = payload["scenario_runs"][0]["run_id"]
    elif case == "duplicate-template":
        payload["scenario_runs"][1]["template_id"] = payload["scenario_runs"][0]["template_id"]
    elif case == "run-city":
        payload["scenario_runs"][0]["city_id"] = "changed.city"
    else:
        payload["scenario_runs"][0]["metrics"][0]["id"] = "new.metric"
    with pytest.raises(ValidationError, match=message):
        StandardizedCityBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["entries"][0].update(bundle_ref="../escape.json"),
            "bundle reference",
        ),
        (
            lambda payload: payload["entries"][0].update(
                run_refs=["../escape.json", *payload["entries"][0]["run_refs"][1:]]
            ),
            "safe relative",
        ),
        (
            lambda payload: payload["entries"][0].update(
                run_hashes=[payload["entries"][0]["run_hashes"][0]] * 3
            ),
            "hashes must be unique",
        ),
    ],
)
def test_tier_s_registry_rejects_unsafe_or_ambiguous_references(
    mutation: object, message: str
) -> None:
    payload = json.loads((OUTPUT / "registry.json").read_text())
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        TierSRegistry.model_validate(payload)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("entry-length", "references, hashes, and statuses must align"),
        ("duplicate-run-reference", "run references must be unique"),
        ("invalid-run-reference", "must use runs/<run-id>.json"),
        ("duplicate-exclusion-reason", "exclusion reasons must be unique"),
        ("target-count", "entries must match target_count"),
        ("selection-order", "selection order must be contiguous"),
        ("duplicate-city", "city identifiers must be unique"),
        ("duplicate-exclusion", "exclusion identifiers and ranks must be unique"),
        ("selected-and-excluded", "both selected and excluded"),
        ("late-exclusion", "exclusions must precede"),
        ("duplicate-climate-parameter", "climate parameters must be unique"),
        ("duplicate-country-indicator", "country indicators must be unique"),
    ],
)
def test_tier_s_registry_cross_record_invariants(case: str, message: str) -> None:
    payload = json.loads((OUTPUT / "registry.json").read_text())
    if case == "entry-length":
        payload["entries"][0]["scenario_statuses"].append("screened")
    elif case == "duplicate-run-reference":
        payload["entries"][0]["run_refs"][1] = payload["entries"][0]["run_refs"][0]
    elif case == "invalid-run-reference":
        payload["entries"][0]["run_refs"][0] = "bad/not-a-run.txt"
    elif case == "duplicate-exclusion-reason":
        reason = payload["exclusions_before_target"][0]["reasons"][0]
        payload["exclusions_before_target"][0]["reasons"] = [reason, reason]
    elif case == "target-count":
        payload["target_count"] -= 1
    elif case == "selection-order":
        payload["entries"][1]["selection_order"] = 1
    elif case == "duplicate-city":
        payload["entries"][1]["city_id"] = payload["entries"][0]["city_id"]
        payload["entries"][1]["bundle_ref"] = payload["entries"][0]["bundle_ref"]
    elif case == "duplicate-exclusion":
        payload["exclusions_before_target"].append(payload["exclusions_before_target"][0])
    elif case == "selected-and-excluded":
        payload["exclusions_before_target"][0]["city_id"] = payload["entries"][0]["city_id"]
    elif case == "late-exclusion":
        payload["exclusions_before_target"][0]["tier_g_rank"] = 999
    elif case == "duplicate-climate-parameter":
        payload["required_climate_parameters"].append(payload["required_climate_parameters"][0])
    else:
        payload["required_country_indicators"].append(payload["required_country_indicators"][0])
    with pytest.raises(ValidationError, match=message):
        TierSRegistry.model_validate(payload)


def test_tier_s_low_level_input_guards(tmp_path: Path) -> None:
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(AnalysisError, match="cannot read validated Tier-S input"):
        tier_s_build._read_json(invalid_json)

    valid = {
        "header": {"fill_value": -999},
        "properties": {
            "parameter": {
                name: {"20240101": 1.0} for name in tier_s_build.REQUIRED_CLIMATE_PARAMETERS
            }
        },
    }
    series, fill_value, missing = tier_s_build._daily_series(valid)
    assert set(series) == set(tier_s_build.REQUIRED_CLIMATE_PARAMETERS)
    assert fill_value == -999
    assert missing == 0
    valid["properties"]["parameter"]["T2M"]["20240101"] = -999
    assert tier_s_build._daily_series(valid)[2] == 1
    assert tier_s_build._format_metric(None) == "missing"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "lacks header or properties"),
        ({"header": {}, "properties": {}}, "lacks parameter series"),
        (
            {"header": {}, "properties": {"parameter": {}}},
            "lacks numeric fill value",
        ),
        (
            {"header": {"fill_value": -999}, "properties": {"parameter": {}}},
            "payload lacks T2M",
        ),
        (
            {
                "header": {"fill_value": -999},
                "properties": {
                    "parameter": {
                        name: ({"20240101": "bad"} if name == "T2M" else {})
                        for name in tier_s_build.REQUIRED_CLIMATE_PARAMETERS
                    }
                },
            },
            "series contains an invalid value",
        ),
        (
            {
                "header": {"fill_value": -999},
                "properties": {
                    "parameter": {
                        name: ({"20240101": float("nan")} if name == "T2M" else {})
                        for name in tier_s_build.REQUIRED_CLIMATE_PARAMETERS
                    }
                },
            },
            "series contains a non-finite value",
        ),
    ],
)
def test_daily_series_rejects_malformed_payloads(payload: dict[str, object], message: str) -> None:
    with pytest.raises(AnalysisError, match=message):
        tier_s_build._daily_series(payload)


def _copy_manifest_pair(source: Path, target: Path) -> tuple[Path, dict[str, object]]:
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(source.read_text())
    artifact = source.parent / str(manifest["artifact_path"])
    destination = target / source.name
    shutil.copyfile(artifact, target / artifact.name)
    destination.write_text(json.dumps(manifest), encoding="utf-8")
    return destination, manifest


def _copy_manifest_directory(source: Path, target: Path) -> list[Path]:
    copied: list[Path] = []
    for manifest_path in sorted(source.glob("*.manifest.json")):
        destination, _ = _copy_manifest_pair(manifest_path, target)
        copied.append(destination)
    return copied


def _replace_artifact_payload(
    manifest_path: Path, manifest: dict[str, object], payload: object
) -> None:
    artifact = manifest_path.parent / str(manifest["artifact_path"])
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    manifest["content_hash"] = tier_s_build.sha256_file(artifact)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("invalid-query", "invalid NASA POWER Tier-S query"),
        ("wrong-contract", "does not match the standard contract"),
    ],
)
def test_climate_loader_rejects_nonstandard_manifests(
    tmp_path: Path, case: str, message: str
) -> None:
    source = next(CLIMATE.glob("*.manifest.json"))
    destination, manifest = _copy_manifest_pair(source, tmp_path)
    query = manifest["query"]
    assert isinstance(query, dict)
    if case == "invalid-query":
        query["parameters"] = []
    else:
        query["parameters"][0], query["parameters"][1] = (
            query["parameters"][1],
            query["parameters"][0],
        )
    destination.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AnalysisError, match=message):
        tier_s_build._load_climate_artifacts(tmp_path)


def test_climate_match_rejects_duplicate_coordinate_artifacts() -> None:
    artifacts = tier_s_build._load_climate_artifacts(CLIMATE)
    catalog = tier_s_build.validate_document(CATALOG, tier_s_build.GlobalCityCatalog)
    artifact = artifacts[0]
    query = artifact[2]
    city = next(
        item
        for item in catalog.cities
        if item.location.latitude == query.latitude and item.location.longitude == query.longitude
    )
    with pytest.raises(AnalysisError, match="multiple NASA POWER artifacts"):
        tier_s_build._match_climate(city, [artifact, artifact])


def test_climate_loader_rejects_non_object_artifact(tmp_path: Path) -> None:
    source = next(CLIMATE.glob("*.manifest.json"))
    destination, manifest = _copy_manifest_pair(source, tmp_path)
    _replace_artifact_payload(destination, manifest, [])
    with pytest.raises(AnalysisError, match="artifact must be an object"):
        tier_s_build._load_climate_artifacts(tmp_path)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("invalid-query", "invalid World Bank Tier-S query"),
        ("unexpected-indicator", "unexpected Tier-S country indicator"),
        ("wrong-year", "must be 2023 all-country pages"),
        ("duplicate-indicator", "duplicate Tier-S indicator page"),
        ("bad-shape", "unexpected shape"),
        ("non-object-row", "record must be an object"),
        ("non-finite-value", "value must be finite"),
    ],
)
def test_country_context_loader_rejects_nonstandard_sources(
    tmp_path: Path, case: str, message: str
) -> None:
    manifests = _copy_manifest_directory(CONTEXT, tmp_path)
    target_index = 1 if case == "duplicate-indicator" else 0
    target = manifests[target_index]
    payload = json.loads(target.read_text())
    query = payload["query"]
    assert isinstance(query, dict)
    if case == "invalid-query":
        query["indicator"] = "not an indicator"
        target.write_text(json.dumps(payload), encoding="utf-8")
    elif case == "unexpected-indicator":
        query["indicator"] = "SP.BAD.TEST"
        target.write_text(json.dumps(payload), encoding="utf-8")
    elif case == "wrong-year":
        query["start_year"] = 2022
        query["end_year"] = 2022
        target.write_text(json.dumps(payload), encoding="utf-8")
    elif case == "duplicate-indicator":
        first_payload = json.loads(manifests[0].read_text())
        query["indicator"] = first_payload["query"]["indicator"]
        target.write_text(json.dumps(payload), encoding="utf-8")
    elif case == "bad-shape":
        _replace_artifact_payload(target, payload, {})
    elif case == "non-object-row":
        _replace_artifact_payload(target, payload, [{}, ["not-an-object"]])
    else:
        artifact_path = target.parent / str(payload["artifact_path"])
        artifact_payload = json.loads(artifact_path.read_text())
        first_numeric = next(row for row in artifact_payload[1] if row["value"] is not None)
        first_numeric["value"] = float("nan")
        _replace_artifact_payload(target, payload, artifact_payload)
    with pytest.raises(AnalysisError, match=message):
        tier_s_build._load_country_context(tmp_path)


def test_tier_s_build_fails_closed_when_required_quality_gate_fails(
    tmp_path: Path,
) -> None:
    artifacts = tier_s_build._load_climate_artifacts(CLIMATE)
    catalog = tier_s_build.validate_document(CATALOG, tier_s_build.GlobalCityCatalog)
    first_city = catalog.cities[0]
    matching_path = next(
        path
        for path, _, query, _ in artifacts
        if query.latitude == first_city.location.latitude
        and query.longitude == first_city.location.longitude
    )
    climate = tmp_path / "climate"
    destination, manifest = _copy_manifest_pair(matching_path, climate)
    manifest["record_count"] = 1
    destination.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AnalysisError, match="required quality gates failed"):
        build_tier_s_registry(CATALOG, climate, CONTEXT, target_count=1)


def test_quality_report_fails_when_response_coordinates_are_absent() -> None:
    artifacts = tier_s_build._load_climate_artifacts(CLIMATE)
    path, manifest, query, payload = artifacts[0]
    assert path.exists()
    catalog = tier_s_build.validate_document(CATALOG, tier_s_build.GlobalCityCatalog)
    city = next(
        item
        for item in catalog.cities
        if item.location.latitude == query.latitude and item.location.longitude == query.longitude
    )
    series, _, missing = tier_s_build._daily_series(payload)
    payload_without_geometry = dict(payload)
    payload_without_geometry.pop("geometry", None)
    report = tier_s_build._build_quality_report(
        city, manifest, query, payload_without_geometry, series, missing
    )
    assert report.overall_status is QualityStatus.FAIL
    assert next(item for item in report.checks if item.id == "coordinate-rounding").measured is None

    wrong_calendar = {name: dict(values) for name, values in series.items()}
    for values in wrong_calendar.values():
        value = values.pop("20240101")
        values["20250101"] = value
    calendar_report = tier_s_build._build_quality_report(
        city, manifest, query, payload, wrong_calendar, missing
    )
    calendar_check = next(
        item for item in calendar_report.checks if item.id == "aligned-daily-keys"
    )
    assert calendar_check.measured == 366
    assert calendar_check.status is QualityStatus.FAIL


def test_tier_s_build_records_missing_climate_exclusions(tmp_path: Path) -> None:
    empty_climate = tmp_path / "empty-climate"
    empty_climate.mkdir()
    with pytest.raises(AnalysisError, match="only 0 cities"):
        build_tier_s_registry(CATALOG, empty_climate, CONTEXT, target_count=1)


def test_tier_s_build_records_missing_context_with_available_climate(
    tmp_path: Path,
) -> None:
    artifacts = tier_s_build._load_climate_artifacts(CLIMATE)
    catalog = tier_s_build.validate_document(CATALOG, tier_s_build.GlobalCityCatalog)
    first_city = catalog.cities[0]
    matching_path = next(
        path
        for path, _, query, _ in artifacts
        if query.latitude == first_city.location.latitude
        and query.longitude == first_city.location.longitude
    )
    climate = tmp_path / "climate"
    _copy_manifest_pair(matching_path, climate)

    context = tmp_path / "context"
    manifests = _copy_manifest_directory(CONTEXT, context)
    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text())
    artifact_path = context / str(manifest["artifact_path"])
    artifact_payload = json.loads(artifact_path.read_text())
    rows = artifact_payload[1]
    target_row = next(row for row in rows if row["country"]["id"] == first_city.country_code)
    target_row["value"] = None
    _replace_artifact_payload(manifest_path, manifest, artifact_payload)

    with pytest.raises(AnalysisError, match="only 0 cities"):
        build_tier_s_registry(CATALOG, climate, context, target_count=1)


def test_tier_s_build_and_writer_reject_invalid_counts(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="target_count must be positive"):
        build_tier_s_registry(CATALOG, CLIMATE, CONTEXT, target_count=0)
    registry, _ = build_tier_s_registry(CATALOG, CLIMATE, CONTEXT, target_count=1)
    with pytest.raises(AnalysisError, match="bundle count does not match"):
        write_tier_s_artifacts(registry, [], tmp_path)
