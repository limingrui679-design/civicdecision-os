from __future__ import annotations

from collections import Counter

import pytest
from pydantic import BaseModel, ValidationError

from civicdecision.deep.models import ApplicationSuite
from civicdecision.product.models import Pagination, ProductTier, ScenarioKind, ScenarioStatus
from civicdecision.product.store import ArtifactStore, ProductNotFoundError
from civicdecision.scenario_library import (
    CurrentReadiness,
    DecisionType,
    ImplementationStatus,
)


def test_catalog_summary_reconciles_committed_scale(product_store: ArtifactStore) -> None:
    summary = product_store.summary
    assert summary.tier_g_cities == 250
    assert summary.tier_s_cities == 30
    assert summary.tier_d_cities == 8
    assert summary.exposed_city_records == 258
    assert summary.tier_assignments == 288
    assert summary.source_artifacts == 90
    assert summary.standard_scenario_screens == 90
    assert summary.scenario_library_designs == 240
    assert summary.scenario_library_families == 30
    assert (summary.reference_implemented_designs, summary.design_only_scenarios) == (12, 228)
    assert summary.scenario_library_city_bindings == 0
    assert summary.scenario_library_methods_claimed == 0
    assert summary.scenario_library_audit_passed
    assert summary.scenario_library_maximum_similarity == 0.646154
    assert summary.deep_scenario_executions == 96
    assert (summary.completed_deep_executions, summary.negative_deep_executions) == (76, 20)
    assert (summary.decision_packs, summary.completed_decision_packs) == (98, 77)
    assert summary.negative_decision_packs == 21
    assert summary.benchmark_run_artifacts == 145
    assert summary.catalog_fingerprint == product_store.catalog_fingerprint
    assert product_store.etag == product_store.etag_for("/api/v1/meta")
    assert product_store.etag != product_store.etag_for("/api/v1/designs")
    assert product_store.etag_for(
        "/api/v1/designs", (("limit", "1"), ("q", "heat"))
    ) != product_store.etag_for("/api/v1/designs", (("limit", "1"), ("q", "cooling")))


@pytest.mark.parametrize(
    ("tier", "expected"),
    [(ProductTier.GLOBAL, 250), (ProductTier.STANDARDIZED, 30), (ProductTier.DEEP, 8)],
)
def test_city_tiers_have_exact_counts(
    product_store: ArtifactStore, tier: ProductTier, expected: int
) -> None:
    page = product_store.list_cities(tier=tier, limit=100)
    assert page.pagination.total == expected
    if expected > 100:
        second = product_store.list_cities(tier=tier, limit=100, offset=100)
        third = product_store.list_cities(tier=tier, limit=100, offset=200)
        assert len(page.items) + len(second.items) + len(third.items) == expected
    assert all(item.tier is tier for item in page.items)


def test_highest_tier_city_projection_deduplicates_overlapping_cities(
    product_store: ArtifactStore,
) -> None:
    pages = [product_store.list_cities(limit=100, offset=offset) for offset in (0, 100, 200)]
    cities = [item for page in pages for item in page.items]
    assert len(cities) == 258
    assert len({item.city_id for item in cities}) == 258
    assert Counter(item.tier for item in cities) == {
        ProductTier.GLOBAL: 220,
        ProductTier.STANDARDIZED: 30,
        ProductTier.DEEP: 8,
    }


def test_city_filtering_is_case_insensitive_and_country_normalized(
    product_store: ArtifactStore,
) -> None:
    page = product_store.list_cities(query="AUSTIN", country_code="us", limit=10)
    assert page.pagination.total == 1
    assert page.items[0].city_id == "us.tx.austin"
    assert page.items[0].tier is ProductTier.DEEP


@pytest.mark.parametrize(
    ("city_id", "tier", "minimum_sources", "minimum_metrics"),
    [
        ("us.tx.austin", ProductTier.DEEP, 7, 10),
        ("geonames.2293538", ProductTier.STANDARDIZED, 5, 5),
        ("geonames.4030723", ProductTier.GLOBAL, 1, 1),
    ],
)
def test_city_detail_projects_each_evidence_tier(
    product_store: ArtifactStore,
    city_id: str,
    tier: ProductTier,
    minimum_sources: int,
    minimum_metrics: int,
) -> None:
    detail = product_store.city_detail(city_id)
    assert detail.city.tier is tier
    assert len(detail.source_artifact_ids) >= minimum_sources
    assert len(detail.metrics) >= minimum_metrics
    assert detail.limitations
    assert detail.provenance


def test_scenario_inventory_preserves_kinds_and_statuses(product_store: ArtifactStore) -> None:
    scenarios = product_store.all_scenario_summaries
    assert len(scenarios) == 188
    assert Counter(item.kind for item in scenarios) == {
        ScenarioKind.STANDARD_SCREEN: 90,
        ScenarioKind.DEEP_PACK: 96,
        ScenarioKind.REFERENCE_PACK: 2,
    }
    assert Counter(item.status for item in scenarios) == {
        ScenarioStatus.COMPLETED: 77,
        ScenarioStatus.SCREENED: 60,
        ScenarioStatus.INSUFFICIENT_EVIDENCE: 50,
        ScenarioStatus.INFEASIBLE: 1,
    }


def test_scenario_filters_and_pagination_compose(product_store: ArtifactStore) -> None:
    page = product_store.list_scenarios(
        kind=ScenarioKind.DEEP_PACK,
        city_id="us.tx.austin",
        suite="behavioral-policy-equity",
        status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
        query="causal",
        limit=1,
    )
    assert page.pagination.total == 1
    assert page.items[0].execution_id == "tierd.us.tx.austin.11"
    assert not page.items[0].recommendation_issued
    designs = product_store.list_scenario_designs(
        suite=ApplicationSuite.CLIMATE_DISASTER,
        family_id="climate.extreme-heat",
        decision_type=DecisionType.SITE,
        implementation_status=ImplementationStatus.DESIGN_ONLY,
        current_readiness=CurrentReadiness.BLOCKED_SOURCE,
        query="cooling center",
        limit=1,
    )
    assert designs.pagination.total == 1
    assert designs.items[0].design_id == ("scenario.climate.extreme-heat.cooling-center-network.v1")
    families = product_store.list_scenario_families(
        suite=ApplicationSuite.CLIMATE_DISASTER,
        query="heat",
        limit=1,
    )
    assert families.pagination.total == 1
    assert families.items[0].design_count == 8
    normalized_search = product_store.list_scenario_designs(
        decision_type=DecisionType.EVALUATE,
        query="cool roof",
        limit=100,
    )
    assert normalized_search.pagination.total == 1
    assert normalized_search.items[0].title == "Evaluate a cool-roof and household-cooling program"


def test_scenario_detail_separates_screen_deep_and_reference_claims(
    product_store: ArtifactStore,
) -> None:
    standard = product_store.scenario_detail("geonames.2293538.screen.heat.2024")
    deep = product_store.scenario_detail("tierd.us.tx.austin.11")
    reference = product_store.scenario_detail("run-aff7c38b12c1")
    assert standard.payload_schema == "standard-scenario-run.schema.json"
    assert standard.artifact_hashes == {}
    assert any("descriptive" in item for item in standard.claim_boundary)
    assert deep.payload_schema == "deep-scenario-pack.schema.json"
    assert set(deep.artifact_hashes) == {"policy-scenario", "decision-pack", "decision-brief"}
    assert deep.scenario.status is ScenarioStatus.INSUFFICIENT_EVIDENCE
    assert reference.payload_schema == "decision-pack.schema.json"
    assert reference.scenario.kind is ScenarioKind.REFERENCE_PACK
    design = product_store.scenario_design_detail(
        "scenario.climate.extreme-heat.heat-access-gaps.v1"
    )
    family = product_store.scenario_family_detail("climate.extreme-heat")
    evidence = product_store.scenario_library_evidence()
    assert design.design.city_bindings == [] and design.design.method_claimed is False
    assert design.design.family_id == design.family.family_id
    assert len(family.designs) == 8
    assert [item.decision_type for item in family.designs] == list(DecisionType)
    assert evidence.audit_passed and evidence.design_count == 240
    assert evidence.high_similarity_pair_count == evidence.exact_signature_collision_count == 0


def test_decision_pack_projection_excludes_standard_screens(product_store: ArtifactStore) -> None:
    page = product_store.list_decision_packs(limit=100)
    assert page.pagination.total == 98
    assert all(item.kind is not ScenarioKind.STANDARD_SCREEN for item in page.items)
    negative = product_store.list_decision_packs(
        status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
        query="causal",
        limit=100,
    )
    assert negative.pagination.total == 8
    with pytest.raises(ProductNotFoundError, match="deliberately not a DecisionPack"):
        product_store.decision_pack("geonames.2293538.screen.heat.2024")


def test_decision_pack_and_brief_are_available_for_deep_and_reference_runs(
    product_store: ArtifactStore,
) -> None:
    for execution_id in ("tierd.us.tx.austin.01", "run-aff7c38b12c1"):
        pack = product_store.decision_pack(execution_id)
        brief = product_store.decision_brief(execution_id)
        assert pack.scenario_id
        assert "#" in brief


def test_source_inventory_is_complete_searchable_and_hash_typed(
    product_store: ArtifactStore,
) -> None:
    first = product_store.list_sources(limit=50)
    second = product_store.list_sources(limit=50, offset=50)
    assert len(first.items) + len(second.items) == 90
    assert sum(item.record_count for item in [*first.items, *second.items]) == 258_478
    assert all(item.content_hash.startswith("sha256:") for item in first.items)
    austin = product_store.list_sources(publisher="austin", query="daily", limit=100)
    assert austin.pagination.total == 2
    assert all(item.publisher == "City of Austin" for item in austin.items)


def test_suite_and_benchmark_overviews_reconcile(product_store: ArtifactStore) -> None:
    suites = product_store.suites()
    benchmark = product_store.benchmark_overview()
    assert len(suites) == 7
    assert sum(item.template_count for item in suites) == 12
    assert sum(item.design_family_count for item in suites) == 30
    assert sum(item.design_count for item in suites) == 240
    assert sum(item.reference_implemented_designs for item in suites) == 12
    assert sum(item.design_only_scenarios for item in suites) == 228
    assert sum(item.execution_count for item in suites) == 96
    assert sum(item.completed_count for item in suites) == 76
    assert sum(item.negative_count for item in suites) == 20
    assert benchmark.run_artifacts == 145
    assert benchmark.historical_replays == 40
    assert benchmark.optimization_tasks == 100
    assert benchmark.optimization_evaluated_plans == 21_710


def test_product_store_rejects_invalid_pagination(product_store: ArtifactStore) -> None:
    cases = [
        ("list_cities", {"limit": 0}),
        ("list_cities", {"offset": -1}),
        ("list_scenarios", {"limit": 101}),
        ("list_scenarios", {"offset": -1}),
        ("list_decision_packs", {"limit": 0}),
        ("list_scenario_designs", {"limit": 101}),
        ("list_scenario_families", {"offset": -1}),
        ("list_sources", {"offset": -1}),
    ]
    for method, kwargs in cases:
        with pytest.raises(ValueError, match=r"(?i)pagination"):
            getattr(product_store, method)(**kwargs)


def test_product_store_not_found_failures_are_typed(product_store: ArtifactStore) -> None:
    cases = [
        ("city_detail", "unknown.city"),
        ("scenario_detail", "unknown.scenario"),
        ("decision_pack", "unknown.pack"),
        ("decision_brief", "unknown.brief"),
        ("scenario_design_detail", "unknown.design"),
        ("scenario_family_detail", "unknown.family"),
    ]
    for method, identifier in cases:
        with pytest.raises(ProductNotFoundError):
            getattr(product_store, method)(identifier)


def test_pagination_contract_rejects_inconsistent_pages(product_store: ArtifactStore) -> None:
    def reject(model: BaseModel, payload: dict[str, object], message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            type(model).model_validate(payload)

    assert Pagination(total=5, limit=2, offset=4, returned=1, next_offset=None)
    with pytest.raises(ValidationError, match="returned count"):
        Pagination(total=5, limit=2, offset=0, returned=1, next_offset=1)
    with pytest.raises(ValidationError, match="next offset"):
        Pagination(total=5, limit=2, offset=0, returned=2, next_offset=None)

    summary = product_store.summary
    summary_base = summary.model_dump(mode="json")
    summary_mutations: list[tuple[str, str, int]] = [
        ("tier_assignments", "catalog tier assignments must reconcile", 1),
        ("deep_scenario_executions", "deep scenario status counts must reconcile", 1),
        ("decision_packs", "DecisionPack status counts must reconcile", 1),
        (
            "reference_implemented_designs",
            "scenario library implementation counts must reconcile",
            1,
        ),
    ]
    for field, message, delta in summary_mutations:
        payload = summary.model_dump(mode="json")
        payload[field] += delta
        reject(summary, payload, message)

    family_matrix_drift = dict(summary_base)
    family_matrix_drift["scenario_library_designs"] = 232
    family_matrix_drift["design_only_scenarios"] = 220
    reject(summary, family_matrix_drift, "eight designs per family")

    austin = product_store.city_detail("us.tx.austin")
    bad_city = austin.city.model_dump(mode="json")
    bad_city["scenario_count"] = 0
    reject(austin.city, bad_city, "city scenario status counts exceed scenario count")

    unsorted_sources = austin.model_dump(mode="json")
    unsorted_sources["source_ids"] = list(reversed(unsorted_sources["source_ids"]))
    reject(austin, unsorted_sources, "source identifiers must be sorted and unique")

    standard = product_store.scenario_detail("geonames.2293538.screen.heat.2024").scenario
    standard_recommendation = standard.model_dump(mode="json")
    standard_recommendation["recommendation_issued"] = True
    standard_recommendation["selected_option_id"] = "option.unverified"
    reject(standard, standard_recommendation, "standard screens cannot issue recommendations")

    completed = product_store.scenario_detail("tierd.us.tx.austin.01").scenario
    recommendation_mismatch = completed.model_dump(mode="json")
    recommendation_mismatch["recommendation_issued"] = False
    reject(completed, recommendation_mismatch, "recommendation flag must match selected option")

    page_models = [
        product_store.list_cities(limit=1),
        product_store.list_scenarios(limit=1),
        product_store.list_scenario_designs(limit=1),
        product_store.list_scenario_families(limit=1),
        product_store.list_sources(limit=1),
    ]
    page_messages = [
        "city page item count must match pagination",
        "scenario page item count must match pagination",
        "scenario design page item count must match pagination",
        "scenario family page item count must match pagination",
        "source page item count must match pagination",
    ]
    for page, message in zip(page_models, page_messages, strict=True):
        payload = page.model_dump(mode="json")
        payload["items"] = []
        reject(page, payload, message)

    family_summary = product_store.list_scenario_families(limit=1).items[0]
    bad_family_summary = family_summary.model_dump(mode="json")
    bad_family_summary["design_count"] += 1
    reject(family_summary, bad_family_summary, "family implementation counts must reconcile")

    design_detail = product_store.scenario_design_detail(
        "scenario.climate.extreme-heat.heat-access-gaps.v1"
    )
    wrong_family = design_detail.model_dump(mode="json")
    wrong_family["family"]["family_id"] = "synthetic.unrelated-family"
    reject(design_detail, wrong_family, "family must match the design")

    missing_design_ref = design_detail.model_dump(mode="json")
    missing_design_ref["family"]["design_refs"][0] = "scenario.synthetic.absent-design.v1"
    reject(design_detail, missing_design_ref, "family must reference the design")

    family_detail = product_store.scenario_family_detail("climate.extreme-heat")
    wrong_design_order = family_detail.model_dump(mode="json")
    wrong_design_order["designs"][0], wrong_design_order["designs"][1] = (
        wrong_design_order["designs"][1],
        wrong_design_order["designs"][0],
    )
    reject(family_detail, wrong_design_order, "must follow registered references")

    library_evidence = product_store.scenario_library_evidence()
    bad_library_total = library_evidence.model_dump(mode="json")
    bad_library_total["design_count"] += 1
    reject(library_evidence, bad_library_total, "implementation counts must reconcile")

    deep_detail = product_store.scenario_detail("tierd.us.tx.austin.01")
    bad_artifact_hash = deep_detail.model_dump(mode="json")
    first_hash = next(iter(bad_artifact_hash["artifact_hashes"]))
    bad_artifact_hash["artifact_hashes"][first_hash] = "not-a-sha256"
    reject(deep_detail, bad_artifact_hash, "artifact hashes must be SHA-256 values")

    suite = product_store.suites()[0]
    bad_execution_total = suite.model_dump(mode="json")
    bad_execution_total["execution_count"] += 1
    reject(suite, bad_execution_total, "suite execution statuses must reconcile")

    bad_design_total = suite.model_dump(mode="json")
    bad_design_total["design_count"] += 1
    reject(suite, bad_design_total, "suite scenario-design statuses must reconcile")
