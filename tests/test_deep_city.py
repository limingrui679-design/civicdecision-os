from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import TextIO

import pytest
from pydantic import ValidationError

from civicdecision.deep.build import build_tier_d_artifacts
from civicdecision.deep.fetch import fetch_tier_d_context, fetch_tier_d_sources
from civicdecision.deep.load import (
    LoadedDeepCity,
    capability_assessments,
    city_metrics,
    load_tier_d_evidence,
    quality_report,
    source_bindings,
)
from civicdecision.deep.models import (
    ApplicationSuite,
    DeepCityBundle,
    DeepScenarioPack,
    DeepScenarioStatus,
    ScenarioCompletionStrategy,
    SourceRole,
    TierDEvidenceSummary,
    TierDRegistry,
)
from civicdecision.deep.specs import DEEP_CITY_SPECS
from civicdecision.deep.templates import DEEP_SCENARIO_TEMPLATES
from civicdecision.protocols.base import sha256_file
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.standardized.models import QualityStatus

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = ROOT / "examples/data/tier-d"
OUTPUT_DIRECTORY = ROOT / "catalog/deep-cities"
CITY_IDS = [item.city_id for item in DEEP_CITY_SPECS]
TEMPLATE_IDS = [item.template_id for item in DEEP_SCENARIO_TEMPLATES]
PACK_CASES = [
    (city_id, template.template_order, template.template_id)
    for city_id in CITY_IDS
    for template in DEEP_SCENARIO_TEMPLATES
]


@pytest.fixture(scope="session")
def loaded_cities() -> dict[str, LoadedDeepCity]:
    return {item.spec.city_id: item for item in load_tier_d_evidence(SOURCE_DIRECTORY)}


@pytest.fixture(scope="session")
def registry() -> TierDRegistry:
    return TierDRegistry.model_validate_json((OUTPUT_DIRECTORY / "registry.json").read_bytes())


@pytest.fixture(scope="session")
def evidence_summary() -> TierDEvidenceSummary:
    return TierDEvidenceSummary.model_validate_json(
        (OUTPUT_DIRECTORY / "evidence-summary.json").read_bytes()
    )


def _pack(city_id: str, order: int) -> DeepScenarioPack:
    path = OUTPUT_DIRECTORY / "packs" / f"tierd.{city_id}.{order:02d}" / "pack.json"
    return DeepScenarioPack.model_validate_json(path.read_bytes())


def test_tier_d_registry_declares_exact_scale_and_anti_inflation(
    registry: TierDRegistry, evidence_summary: TierDEvidenceSummary
) -> None:
    assert len(registry.entries) == 8
    assert len(registry.scenario_templates) == 12
    assert registry.total_scenario_packs == 96
    assert evidence_summary.nonduplicative_scenario_designs == 12
    assert evidence_summary.city_bound_scenario_executions == 96
    assert evidence_summary.source_manifest_artifacts == 49
    assert evidence_summary.distinct_source_datasets == 11
    assert evidence_summary.deduplicated_underlying_requests == 4_148_633
    assert evidence_summary.completed_scenarios + evidence_summary.negative_scenarios == 96


@pytest.mark.parametrize("template", DEEP_SCENARIO_TEMPLATES, ids=TEMPLATE_IDS)
def test_deep_scenario_template_contract(template: object) -> None:
    typed = next(item for item in DEEP_SCENARIO_TEMPLATES if item is template)
    assert typed.template_order in range(1, 13)
    assert typed.intended_claim
    assert typed.prohibited_claims
    assert typed.assumptions
    assert typed.limitations
    assert typed.required_source_roles
    assert len(typed.evidence_requirements) == len(set(typed.evidence_requirements))
    if typed.completion_strategy is ScenarioCompletionStrategy.CATEGORY_DEMAND:
        assert typed.category_keywords == sorted(set(typed.category_keywords))
        assert typed.minimum_matching_requests > 0
    else:
        assert typed.category_keywords == []
        assert typed.minimum_matching_requests == 0


@pytest.mark.parametrize("city_id", CITY_IDS)
def test_deep_city_source_views_reconcile(
    city_id: str, loaded_cities: dict[str, LoadedDeepCity]
) -> None:
    city = loaded_cities[city_id]
    assert len(city.source_manifests) == 7
    assert len(city.municipal) == 4
    assert {item.underlying_request_count for item in city.municipal.values()} == {
        city.request_count
    }
    assert len(city.daily_request_counts()) == 183
    assert sum(city.daily_request_counts().values()) == city.request_count
    assert sum(city.category_request_counts().values()) == city.request_count
    assert city.population_row.estimate > 0
    assert len(city.climate_series("T2M")) == 183


@pytest.mark.parametrize("city_id", CITY_IDS)
def test_deep_city_quality_metrics_bindings_and_capabilities(
    city_id: str, loaded_cities: dict[str, LoadedDeepCity]
) -> None:
    city = loaded_cities[city_id]
    report = quality_report(city)
    bindings = source_bindings(city)
    metrics = city_metrics(city)
    capabilities = capability_assessments(city)
    assert report.overall_status in {QualityStatus.PASS, QualityStatus.WARN}
    assert len(report.checks) == 10
    assert len(bindings) == 7
    assert len(metrics) == 18
    assert len(capabilities) == 7
    assert {item.capability_id.removeprefix("suite.") for item in capabilities} == {
        item.value for item in ApplicationSuite
    }
    assert {item.role for item in bindings} >= {
        SourceRole.MUNICIPAL_DEMAND,
        SourceRole.CLIMATE_CONTEXT,
        SourceRole.GEOGRAPHIC_IDENTITY,
        SourceRole.DEMOGRAPHIC_CONTEXT,
    }
    assert {item.evidence_type for item in metrics} <= {
        EvidenceType.OBSERVED,
        EvidenceType.ESTIMATED,
    }


@pytest.mark.parametrize(
    ("city_id", "order", "template_id"),
    PACK_CASES,
    ids=[f"{city}-{order:02d}" for city, order, _ in PACK_CASES],
)
def test_every_deep_scenario_pack_validates_and_preserves_status_contract(
    city_id: str,
    order: int,
    template_id: str,
    registry: TierDRegistry,
) -> None:
    pack = _pack(city_id, order)
    template = registry.scenario_templates[order - 1]
    assert pack.pack_id == f"tierd.{city_id}.{order:02d}"
    assert pack.city_id == city_id
    assert pack.scenario_template_id == template_id == template.template_id
    assert pack.suite is template.suite
    assert pack.scenario.scenario_id == pack.pack_id
    assert pack.scenario.city_id == city_id
    assert len(pack.source_refs) == 7
    assert len(pack.assumption_register) >= 3
    assert "not" in pack.decision_brief.lower()
    if pack.status is DeepScenarioStatus.COMPLETED:
        assert pack.forecast is not None and pack.forecast.observation_count == 183
        assert pack.simulation is not None and pack.simulation.config.iterations == 2_500
        assert pack.optimization is not None
        assert pack.optimization.solver.search_space_size == 3_125
        assert pack.optimization.solver.enumeration_complete is True
        assert pack.uncertainty is not None
        assert sum(item.draws for item in pack.uncertainty.option_summaries) == 3_000
        assert pack.decision_pack.status.value == "completed"
        assert pack.decision_pack.reversal_tests
        assert pack.decision_pack.value_of_information
    else:
        assert pack.status is DeepScenarioStatus.INSUFFICIENT_EVIDENCE
        assert pack.forecast is None
        assert pack.simulation is None
        assert pack.optimization is None
        assert pack.uncertainty is None
        assert pack.decision_pack.status.value == "insufficient_evidence"
        assert pack.decision_pack.failure_reason
        assert pack.decision_pack.recommendation.selected_option_id is None


@pytest.mark.parametrize(
    ("city_id", "order", "template_id"),
    PACK_CASES,
    ids=[f"{city}-{order:02d}" for city, order, _ in PACK_CASES],
)
def test_every_deep_scenario_artifact_hash_and_registry_binding(
    city_id: str,
    order: int,
    template_id: str,
    registry: TierDRegistry,
    evidence_summary: TierDEvidenceSummary,
) -> None:
    pack = _pack(city_id, order)
    entry = next(item for item in registry.entries if item.city_id == city_id)
    assert entry.scenario_pack_refs[order - 1] == f"packs/{pack.pack_id}/pack.json"
    assert entry.scenario_pack_hashes[order - 1] == pack.content_hash()
    evidence = next(item for item in evidence_summary.scenarios if item.pack_id == pack.pack_id)
    assert evidence.scenario_template_id == template_id
    assert evidence.pack_file_hash == sha256_file(
        OUTPUT_DIRECTORY / entry.scenario_pack_refs[order - 1]
    )
    for reference in pack.analytical_artifacts:
        path = OUTPUT_DIRECTORY / reference.path
        assert path.is_file()
        assert sha256_file(path) == reference.content_hash
        assert evidence.artifact_hashes[reference.kind] == reference.content_hash


@pytest.mark.parametrize("city_id", CITY_IDS)
def test_deep_city_bundle_hash_and_embedded_pack_bindings(
    city_id: str, registry: TierDRegistry
) -> None:
    entry = next(item for item in registry.entries if item.city_id == city_id)
    bundle = DeepCityBundle.model_validate_json((OUTPUT_DIRECTORY / entry.bundle_ref).read_bytes())
    assert bundle.content_hash() == entry.bundle_hash
    assert [item.content_hash() for item in bundle.scenario_packs] == entry.scenario_pack_hashes
    assert bundle.adapter.city_id == city_id
    assert len(bundle.metrics) == 18
    assert len(bundle.capabilities) == 7
    assert len(bundle.source_manifests) == 7


def test_tier_d_resume_fetchers_verify_all_committed_artifacts() -> None:
    municipal = asyncio.run(fetch_tier_d_sources(SOURCE_DIRECTORY, resume=True))
    context = asyncio.run(fetch_tier_d_context(SOURCE_DIRECTORY, resume=True))
    assert municipal.city_count == 8
    assert municipal.aggregation_count == 32
    assert municipal.aggregate_rows == 148_836
    assert context.city_count == 8
    assert context.artifact_count == 17
    assert context.declared_source_units == 8_800


@pytest.mark.parametrize(
    ("function", "kwargs", "message"),
    [
        (fetch_tier_d_sources, {"attempts": 0}, "at least one attempt"),
        (fetch_tier_d_sources, {"concurrency": 0}, "between one and eight"),
        (fetch_tier_d_sources, {"concurrency": 9}, "between one and eight"),
        (fetch_tier_d_context, {"attempts": 0}, "at least one attempt"),
        (fetch_tier_d_context, {"concurrency": 0}, "between one and eight"),
        (fetch_tier_d_context, {"concurrency": 9}, "between one and eight"),
    ],
)
def test_tier_d_fetch_parameter_gates(
    function: object, kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        asyncio.run(function(SOURCE_DIRECTORY, **kwargs))  # type: ignore[operator]


def test_tier_d_model_rejects_registry_template_count_drift(registry: TierDRegistry) -> None:
    payload = registry.model_dump(mode="json")
    payload["scenario_templates"] = payload["scenario_templates"][:-1]
    with pytest.raises(ValidationError):
        TierDRegistry.model_validate(payload)


def test_tier_d_model_rejects_evidence_workload_drift(
    evidence_summary: TierDEvidenceSummary,
) -> None:
    payload = evidence_summary.model_dump(mode="json")
    payload["total_simulation_iterations"] += 1
    with pytest.raises(ValidationError, match="does not reconcile"):
        TierDEvidenceSummary.model_validate(payload)


def test_tier_d_exact_rebuild_matches_committed_tree(tmp_path: Path) -> None:
    rebuilt = tmp_path / "deep-cities"
    artifacts = build_tier_d_artifacts(SOURCE_DIRECTORY, rebuilt)
    expected_files = {
        path.relative_to(OUTPUT_DIRECTORY).as_posix()
        for path in OUTPUT_DIRECTORY.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(rebuilt).as_posix() for path in rebuilt.rglob("*") if path.is_file()
    }
    assert actual_files == expected_files
    for relative in sorted(expected_files):
        assert (rebuilt / relative).read_bytes() == (OUTPUT_DIRECTORY / relative).read_bytes()
    assert len(artifacts.scenario_pack_paths) == 96


def test_tier_d_ledgers_are_row_complete(evidence_summary: TierDEvidenceSummary) -> None:
    with (OUTPUT_DIRECTORY / "scenario-ledger.csv").open(newline="", encoding="utf-8") as handle:
        scenarios = list(csv_dict_reader(handle))
    with (OUTPUT_DIRECTORY / "source-evidence.csv").open(newline="", encoding="utf-8") as handle:
        sources = list(csv_dict_reader(handle))
    with (OUTPUT_DIRECTORY / "cross-city-metrics.csv").open(newline="", encoding="utf-8") as handle:
        metrics = list(csv_dict_reader(handle))
    assert len(scenarios) == 96
    assert len(sources) == 49
    assert len(metrics) == 8 * 18
    assert {row["pack_id"] for row in scenarios} == {
        item.pack_id for item in evidence_summary.scenarios
    }


def csv_dict_reader(handle: TextIO) -> list[dict[str, str]]:
    return list(csv.DictReader(handle))


def test_tier_d_json_ledgers_are_canonical() -> None:
    for filename in ("registry.json", "evidence-summary.json"):
        payload = json.loads((OUTPUT_DIRECTORY / filename).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert payload["schema_version"] == "1.0.0"
