from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from civicdecision.deep.models import (
    CapabilityAssessment,
    DeepCityBundle,
    DeepMetric,
    DeepScenarioPack,
    DeepScenarioStatus,
    DeepScenarioTemplate,
    DeepSourceBinding,
    ScenarioArtifactRef,
    TierDEvidenceSummary,
    TierDRegistry,
    TierDRegistryEntry,
    TierDScenarioEvidence,
)

ROOT = Path(__file__).resolve().parents[1]
DEEP_ROOT = ROOT / "catalog/deep-cities"
NYC_BUNDLE = DEEP_ROOT / "cities/us.ny.new-york-city/bundle.json"
NYC_COMPLETED = DEEP_ROOT / "packs/tierd.us.ny.new-york-city.01/pack.json"
NYC_NEGATIVE = DEEP_ROOT / "packs/tierd.us.ny.new-york-city.11/pack.json"

Payload = dict[str, Any]
Mutation = Callable[[Payload], None]


def _payload(path: Path) -> Payload:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _mutate(payload: Payload, mutation: Mutation) -> Payload:
    changed = copy.deepcopy(payload)
    mutation(changed)
    return changed


def _set_keywords_unsorted(payload: Payload) -> None:
    payload["category_keywords"] = ["zeta", "alpha"]


def _add_keywords_to_total(payload: Payload) -> None:
    payload["category_keywords"] = ["pothole"]


def _remove_category_gate(payload: Payload) -> None:
    payload["minimum_matching_requests"] = 0


def _duplicate_required_role(payload: Payload) -> None:
    payload["required_source_roles"].append(payload["required_source_roles"][0])


def _duplicate_analysis_mode(payload: Payload) -> None:
    payload["analysis_modes"].append(payload["analysis_modes"][0])


def _duplicate_evidence_requirement(payload: Payload) -> None:
    payload["evidence_requirements"].append(payload["evidence_requirements"][0])


def _remove_causal_requirement(payload: Payload) -> None:
    payload["evidence_requirements"] = [
        item for item in payload["evidence_requirements"] if item != "causal"
    ]


@pytest.mark.parametrize(
    ("base_name", "mutation", "message"),
    [
        ("category", _set_keywords_unsorted, "sorted and unique"),
        ("total", _add_keywords_to_total, "only category-demand"),
        ("category", _remove_category_gate, "positive matching-request gate"),
        ("total", _duplicate_required_role, "source roles must be unique"),
        ("total", _duplicate_analysis_mode, "analysis modes must be unique"),
        ("total", _duplicate_evidence_requirement, "requirements must be unique"),
        ("causal", _remove_causal_requirement, "must require causal evidence"),
    ],
)
def test_deep_template_rejects_each_semantic_drift(
    base_name: str, mutation: Mutation, message: str
) -> None:
    templates = _payload(DEEP_ROOT / "registry.json")["scenario_templates"]
    if base_name == "category":
        base = next(item for item in templates if item["completion_strategy"] == "category-demand")
    elif base_name == "causal":
        base = next(item for item in templates if "causal" in item["analysis_modes"])
    else:
        base = next(item for item in templates if item["completion_strategy"] == "total-demand")
    with pytest.raises(ValidationError, match=message):
        DeepScenarioTemplate.model_validate(_mutate(base, mutation))


def test_deep_source_binding_rejects_unsupported_evidence_upgrade() -> None:
    base = _payload(NYC_BUNDLE)["source_bindings"][0]
    with pytest.raises(ValidationError, match="observed or estimated"):
        DeepSourceBinding.model_validate(
            _mutate(base, lambda item: item.update(evidence_type="simulated"))
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_refs", ["same", "same"], "must be unique"),
        ("evidence_type", "proposed", "observed or estimated"),
    ],
)
def test_deep_metric_rejects_evidence_and_lineage_drift(
    field: str, value: object, message: str
) -> None:
    base = _payload(NYC_BUNDLE)["metrics"][0]
    with pytest.raises(ValidationError, match=message):
        DeepMetric.model_validate(_mutate(base, lambda item: item.update({field: value})))


def _capability_extra_role(payload: Payload) -> None:
    payload["satisfied_source_roles"].append("network")


def _capability_ready_missing(payload: Payload) -> None:
    payload["satisfied_source_roles"] = payload["satisfied_source_roles"][:-1]


def _capability_blocked_complete(payload: Payload) -> None:
    payload["status"] = "blocked"


def _capability_without_evidence(payload: Payload) -> None:
    payload["evidence_refs"] = []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_capability_extra_role, "subset"),
        (_capability_ready_missing, "every required"),
        (_capability_blocked_complete, "cannot satisfy every"),
        (_capability_without_evidence, "must match satisfied roles"),
    ],
)
def test_capability_assessment_rejects_status_evidence_mismatch(
    mutation: Mutation, message: str
) -> None:
    base = next(item for item in _payload(NYC_BUNDLE)["capabilities"] if item["status"] == "ready")
    with pytest.raises(ValidationError, match=message):
        CapabilityAssessment.model_validate(_mutate(base, mutation))


@pytest.mark.parametrize(
    "unsafe_path", ["/absolute/pack.json", "packs/../secret.json", r"packs\bad.json"]
)
def test_scenario_artifact_reference_rejects_unsafe_paths(unsafe_path: str) -> None:
    base = _payload(NYC_COMPLETED)["analytical_artifacts"][0]
    with pytest.raises(ValidationError, match="safe relative POSIX"):
        ScenarioArtifactRef.model_validate(
            _mutate(base, lambda item: item.update(path=unsafe_path))
        )


def _pack_identity(payload: Payload) -> None:
    payload["scenario"]["city_id"] = "us.ma.boston"


def _pack_cutoff(payload: Payload) -> None:
    payload["data_cutoff"] = "2025-09-29T00:00:00Z"


def _pack_decision_identity(payload: Payload) -> None:
    payload["decision_pack"]["scenario_id"] = "tierd.us.ny.new-york-city.02"


def _pack_duplicate_kind(payload: Payload) -> None:
    payload["analytical_artifacts"].append(copy.deepcopy(payload["analytical_artifacts"][0]))


def _pack_missing_brief(payload: Payload) -> None:
    payload["analytical_artifacts"] = [
        item for item in payload["analytical_artifacts"] if item["kind"] != "decision-brief"
    ]


def _pack_unbound_forecast(payload: Payload) -> None:
    payload["analytical_artifacts"] = [
        item for item in payload["analytical_artifacts"] if item["kind"] != "forecast-run"
    ]


def _pack_completed_descriptive(payload: Payload) -> None:
    payload["readiness"] = "descriptive"


def _pack_completed_zero_requests(payload: Payload) -> None:
    payload["observed_request_count"] = 0


def _pack_completed_without_decision_analysis(payload: Payload) -> None:
    payload["optimization"] = None
    payload["uncertainty"] = None
    payload["analytical_artifacts"] = [
        item
        for item in payload["analytical_artifacts"]
        if item["kind"] not in {"optimization-run", "uncertainty-run"}
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_pack_identity, "identity must match"),
        (_pack_cutoff, "cutoff must match"),
        (_pack_decision_identity, "matching DecisionPack"),
        (_pack_duplicate_kind, "kinds must be unique"),
        (_pack_missing_brief, "lacks a required"),
        (_pack_unbound_forecast, "reference and model must align"),
        (_pack_completed_descriptive, "planning-support"),
        (_pack_completed_zero_requests, "require observed municipal requests"),
        (_pack_completed_without_decision_analysis, "require optimization and uncertainty"),
    ],
)
def test_completed_pack_rejects_cross_artifact_and_release_drift(
    mutation: Mutation, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        DeepScenarioPack.model_validate(_mutate(_payload(NYC_COMPLETED), mutation))


def test_completed_pack_rejects_negative_decision_pack() -> None:
    payload = _payload(NYC_COMPLETED)
    negative_decision = _payload(NYC_NEGATIVE)["decision_pack"]
    negative_decision["scenario_id"] = payload["pack_id"]
    payload["decision_pack"] = negative_decision
    with pytest.raises(ValidationError, match="completed DecisionPack"):
        DeepScenarioPack.model_validate(payload)


@pytest.mark.parametrize(
    ("readiness", "message"),
    [
        ("planning-support", "insufficient readiness"),
        ("insufficient-evidence", "cannot embed a completed DecisionPack"),
    ],
)
def test_negative_pack_rejects_readiness_or_completed_release(readiness: str, message: str) -> None:
    payload = _payload(NYC_COMPLETED)
    payload["status"] = "insufficient-evidence"
    payload["readiness"] = readiness
    with pytest.raises(ValidationError, match=message):
        DeepScenarioPack.model_validate(payload)


def _bundle_wrong_tier(payload: Payload) -> None:
    payload["adapter"]["tier"] = "S"


def _bundle_reversed_period(payload: Payload) -> None:
    payload["reference_period_start"] = payload["reference_period_end_exclusive"]


def _bundle_duplicate_manifest(payload: Payload) -> None:
    payload["source_manifests"][1] = copy.deepcopy(payload["source_manifests"][0])


def _bundle_missing_binding(payload: Payload) -> None:
    payload["source_bindings"] = payload["source_bindings"][:-1]


def _bundle_mismatched_binding(payload: Payload) -> None:
    payload["source_bindings"][0]["source_id"] = "different-source"


def _bundle_adapter_source_drift(payload: Payload) -> None:
    payload["adapter"]["source_ids"] = payload["adapter"]["source_ids"][:-1]


def _bundle_missing_role(payload: Payload) -> None:
    for binding in payload["source_bindings"]:
        if binding["role"] == "climate-context":
            binding["role"] = "demographic-context"


def _bundle_failed_quality(payload: Payload) -> None:
    payload["quality_report"]["overall_status"] = "fail"
    payload["quality_report"]["checks"][0]["status"] = "fail"


def _bundle_duplicate_metric(payload: Payload) -> None:
    payload["metrics"][1]["id"] = payload["metrics"][0]["id"]


def _bundle_unknown_metric_source(payload: Payload) -> None:
    payload["metrics"][0]["source_refs"] = ["unknown-artifact"]


def _bundle_duplicate_capability(payload: Payload) -> None:
    payload["capabilities"][1]["capability_id"] = payload["capabilities"][0]["capability_id"]


def _bundle_duplicate_pack(payload: Payload) -> None:
    payload["scenario_packs"][-1] = copy.deepcopy(payload["scenario_packs"][0])


def _bundle_wrong_pack_city(payload: Payload) -> None:
    payload["scenario_packs"][-1]["city_id"] = "us.ma.boston"
    payload["scenario_packs"][-1]["scenario"]["city_id"] = "us.ma.boston"


def _bundle_missing_suite(payload: Payload) -> None:
    counts = Counter(item["suite"] for item in payload["scenario_packs"])
    unique_suite = next(suite for suite, count in counts.items() if count == 1)
    target = next(item for item in payload["scenario_packs"] if item["suite"] == unique_suite)
    target["suite"] = next(suite for suite in counts if suite != unique_suite)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_bundle_wrong_tier, "Tier-D adapter"),
        (_bundle_reversed_period, "reference period must be ordered"),
        (_bundle_duplicate_manifest, "identifiers must be unique"),
        (_bundle_missing_binding, "cover each manifest exactly"),
        (_bundle_mismatched_binding, "does not match its manifest"),
        (_bundle_adapter_source_drift, "source IDs must match"),
        (_bundle_missing_role, "lacks a required source role"),
        (_bundle_failed_quality, "cannot pass with a failed"),
        (_bundle_duplicate_metric, "metric identifiers must be unique"),
        (_bundle_unknown_metric_source, "undeclared source artifact"),
        (_bundle_duplicate_capability, "capability identifiers must be unique"),
        (_bundle_duplicate_pack, "packs and templates must be unique"),
        (_bundle_wrong_pack_city, "scenario city must match"),
        (_bundle_missing_suite, "cover all seven"),
    ],
)
def test_deep_bundle_rejects_cross_layer_integrity_drift(mutation: Mutation, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        DeepCityBundle.model_validate(_mutate(_payload(NYC_BUNDLE), mutation))


def test_deep_bundle_requires_at_least_one_completed_scenario() -> None:
    bundle = DeepCityBundle.model_validate(_payload(NYC_BUNDLE))
    negative_packs = [
        item.model_copy(update={"status": DeepScenarioStatus.INSUFFICIENT_EVIDENCE})
        for item in bundle.scenario_packs
    ]
    changed = bundle.model_copy(update={"scenario_packs": negative_packs})
    with pytest.raises(ValueError, match="at least one completed"):
        changed.deep_bundle_integrity()


def _entry_duplicate_ref(payload: Payload) -> None:
    payload["scenario_pack_refs"][-1] = payload["scenario_pack_refs"][0]


def _entry_wrong_outcome_total(payload: Payload) -> None:
    payload["completed_scenarios"] = 0
    payload["negative_scenarios"] = 11


def _entry_wrong_bundle(payload: Payload) -> None:
    payload["bundle_ref"] = "cities/other/bundle.json"


def _entry_unsafe_ref(payload: Payload) -> None:
    payload["scenario_pack_refs"][-1] = "packs/../private/pack.json"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_entry_duplicate_ref, "references must be unique"),
        (_entry_wrong_outcome_total, "must total twelve"),
        (_entry_wrong_bundle, "must match the city ID"),
        (_entry_unsafe_ref, "safe relative paths"),
    ],
)
def test_registry_entry_rejects_count_and_path_drift(mutation: Mutation, message: str) -> None:
    base = _payload(DEEP_ROOT / "registry.json")["entries"][0]
    with pytest.raises(ValidationError, match=message):
        TierDRegistryEntry.model_validate(_mutate(base, mutation))


def _registry_reversed_period(payload: Payload) -> None:
    payload["reference_period_start"] = payload["reference_period_end_exclusive"]


def _registry_noncontiguous_order(payload: Payload) -> None:
    payload["entries"][0]["selection_order"] = 2


def _registry_duplicate_city(payload: Payload) -> None:
    payload["entries"][1]["city_id"] = payload["entries"][0]["city_id"]
    payload["entries"][1]["bundle_ref"] = payload["entries"][0]["bundle_ref"]


def _registry_bad_template_order(payload: Payload) -> None:
    payload["scenario_templates"][1]["template_order"] = 1


def _registry_duplicate_template(payload: Payload) -> None:
    payload["scenario_templates"][1]["template_id"] = payload["scenario_templates"][0][
        "template_id"
    ]


def _registry_request_drift(payload: Payload) -> None:
    payload["total_underlying_requests"] += 1


def _registry_platform_drift(payload: Payload) -> None:
    payload["platform_counts"]["socrata"] += 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_registry_reversed_period, "reference period must be ordered"),
        (_registry_noncontiguous_order, "selection order must be contiguous"),
        (_registry_duplicate_city, "city IDs must be unique"),
        (_registry_bad_template_order, "template order must be contiguous"),
        (_registry_duplicate_template, "template identifiers must be unique"),
        (_registry_request_drift, "request total must reconcile"),
        (_registry_platform_drift, "platform counts must reconcile"),
    ],
)
def test_registry_rejects_scale_and_reconciliation_drift(mutation: Mutation, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TierDRegistry.model_validate(_mutate(_payload(DEEP_ROOT / "registry.json"), mutation))


def _evidence_invalid_hash(payload: Payload) -> None:
    first = next(iter(payload["artifact_hashes"]))
    payload["artifact_hashes"][first] = "not-a-hash"


def _evidence_evaluated_over_search(payload: Payload) -> None:
    payload["optimization_evaluated_plans"] = payload["optimization_search_space"] + 1


def _evidence_feasible_over_evaluated(payload: Payload) -> None:
    payload["optimization_feasible_plans"] = payload["optimization_evaluated_plans"] + 1


def _evidence_completed_zero_work(payload: Payload) -> None:
    payload["forecast_input_observations"] = 0


def _evidence_negative_work(payload: Payload) -> None:
    payload["forecast_input_observations"] = 1


@pytest.mark.parametrize(
    ("base_kind", "mutation", "message"),
    [
        ("completed", _evidence_invalid_hash, "must be SHA-256"),
        ("completed", _evidence_evaluated_over_search, "exceeds its search space"),
        ("completed", _evidence_feasible_over_evaluated, "exceed evaluated plans"),
        ("completed", _evidence_completed_zero_work, "record every analytical workload"),
        ("negative", _evidence_negative_work, "cannot claim completed analytical workload"),
    ],
)
def test_scenario_evidence_rejects_hash_and_workload_drift(
    base_kind: str, mutation: Mutation, message: str
) -> None:
    scenarios = _payload(DEEP_ROOT / "evidence-summary.json")["scenarios"]
    status = "completed" if base_kind == "completed" else "insufficient-evidence"
    base = next(item for item in scenarios if item["status"] == status)
    with pytest.raises(ValidationError, match=message):
        TierDScenarioEvidence.model_validate(_mutate(base, mutation))


def _summary_invalid_source_hash(payload: Payload) -> None:
    first = next(iter(payload["source_artifact_hashes"]))
    payload["source_artifact_hashes"][first] = "bad"


def _summary_duplicate_pack(payload: Payload) -> None:
    payload["scenarios"][1] = copy.deepcopy(payload["scenarios"][0])


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_summary_invalid_source_hash, "must be SHA-256"),
        (_summary_duplicate_pack, "identifiers must be unique"),
    ],
)
def test_evidence_summary_rejects_source_hash_and_pack_identity_drift(
    mutation: Mutation, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        TierDEvidenceSummary.model_validate(
            _mutate(_payload(DEEP_ROOT / "evidence-summary.json"), mutation)
        )
