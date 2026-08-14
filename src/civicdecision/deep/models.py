"""Strict Tier-D city, scenario-pack, and release-registry contracts."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal, cast

from pydantic import Field, field_validator, model_validator

from civicdecision.analysis.forecasting import ForecastRun
from civicdecision.analysis.simulation import SimulationRun
from civicdecision.analysis.uncertainty import UncertaintyRun
from civicdecision.optimization.portfolio import PortfolioOptimizationRun
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    JsonValue,
    StrictModel,
    canonical_json,
    ensure_aware,
    normalize_float,
    normalize_json_floats,
    sha256_bytes,
)
from civicdecision.protocols.city import CityAdapterManifest, CityTier
from civicdecision.protocols.decision import DecisionPack
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.scenario import AnalysisMode, PolicyScenario
from civicdecision.protocols.source import SourceManifest
from civicdecision.standardized.models import DataQualityReport, QualityStatus

SHA256_VALUE_PATTERN = r"^sha256:[0-9a-f]{64}$"
TIER_D_FLOAT_SIGNIFICANT_DIGITS = 12


def tier_d_canonical_json(value: StrictModel | JsonValue | dict[str, Any]) -> bytes:
    """Serialize Tier-D evidence with platform-neutral float precision."""

    return canonical_json(
        value,
        float_significant_digits=TIER_D_FLOAT_SIGNIFICANT_DIGITS,
    )


def tier_d_content_hash(value: StrictModel) -> str:
    """Hash the platform-neutral Tier-D representation."""

    return sha256_bytes(tier_d_canonical_json(value))


def tier_d_json_value(value: JsonValue) -> JsonValue:
    """Normalize one JSON value for Tier-D text and tabular artifacts."""

    return cast(
        JsonValue,
        normalize_json_floats(
            value,
            significant_digits=TIER_D_FLOAT_SIGNIFICANT_DIGITS,
        ),
    )


def tier_d_float(value: float) -> float:
    """Normalize a Tier-D calculation before statistics or hashing."""

    return normalize_float(
        value,
        significant_digits=TIER_D_FLOAT_SIGNIFICANT_DIGITS,
    )


class ApplicationSuite(StrEnum):
    CLIMATE_DISASTER = "climate-disaster-resilience"
    MOBILITY_ACCESS = "mobility-accessibility-operations"
    POPULATION_HEALTH = "population-health-environmental-exposure"
    HOUSING_LAND_USE = "housing-land-use-regeneration"
    PUBLIC_SERVICE = "public-service-operations"
    INFRASTRUCTURE_FINANCE = "infrastructure-finance-asset-risk"
    BEHAVIORAL_EQUITY = "behavioral-policy-equity"


class DeepScenarioStatus(StrEnum):
    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"
    INFEASIBLE = "infeasible"
    FAILED = "failed"


class ReadinessLevel(StrEnum):
    DESCRIPTIVE = "descriptive"
    PLANNING_SUPPORT = "planning-support"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class SourceRole(StrEnum):
    MUNICIPAL_DEMAND = "municipal-demand"
    CLIMATE_CONTEXT = "climate-context"
    GEOGRAPHIC_IDENTITY = "geographic-identity"
    DEMOGRAPHIC_CONTEXT = "demographic-context"
    ASSET_INVENTORY = "asset-inventory"
    NETWORK = "network"


class ScenarioCompletionStrategy(StrEnum):
    TOTAL_DEMAND = "total-demand"
    CATEGORY_DEMAND = "category-demand"
    REQUIRED_CAUSAL_DESIGN = "required-causal-design"
    REQUIRED_NETWORK = "required-network"


class DeepScenarioTemplate(StrictModel):
    template_order: int = Field(ge=1, le=12)
    template_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1)
    completion_strategy: ScenarioCompletionStrategy
    category_keywords: list[str]
    minimum_matching_requests: int = Field(ge=0)
    required_source_roles: list[SourceRole] = Field(min_length=1)
    analysis_modes: list[AnalysisMode] = Field(min_length=1)
    evidence_requirements: list[EvidenceType] = Field(min_length=1)
    intended_claim: str = Field(min_length=1)
    prohibited_claims: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def template_integrity(self) -> DeepScenarioTemplate:
        if self.category_keywords != sorted(set(self.category_keywords)):
            raise ValueError("deep scenario category keywords must be sorted and unique")
        category_strategy = self.completion_strategy is ScenarioCompletionStrategy.CATEGORY_DEMAND
        if category_strategy != bool(self.category_keywords):
            raise ValueError("only category-demand templates may declare category keywords")
        if category_strategy != (self.minimum_matching_requests > 0):
            raise ValueError("category-demand templates require a positive matching-request gate")
        if len(self.required_source_roles) != len(set(self.required_source_roles)):
            raise ValueError("deep scenario required source roles must be unique")
        if len(self.analysis_modes) != len(set(self.analysis_modes)):
            raise ValueError("deep scenario analysis modes must be unique")
        if len(self.evidence_requirements) != len(set(self.evidence_requirements)):
            raise ValueError("deep scenario evidence requirements must be unique")
        if (
            AnalysisMode.CAUSAL in self.analysis_modes
            and EvidenceType.CAUSAL not in self.evidence_requirements
        ):
            raise ValueError("causal deep scenarios must require causal evidence")
        return self


class DeepSourceBinding(StrictModel):
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    role: SourceRole
    evidence_type: EvidenceType
    geographic_scope: str = Field(min_length=1)
    temporal_scope: str = Field(min_length=1)
    record_semantics: str = Field(min_length=1)
    underlying_observation_count: int = Field(ge=0)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def source_is_observed_or_estimated(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OBSERVED, EvidenceType.ESTIMATED}:
            raise ValueError("deep-city source bindings must be observed or estimated")
        return value


class DeepMetric(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    value: int | float | str | None
    unit: str = Field(min_length=1)
    evidence_type: EvidenceType
    source_refs: list[str] = Field(min_length=1)
    method: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("deep metric source references must be unique")
        return value

    @field_validator("evidence_type")
    @classmethod
    def metric_evidence(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OBSERVED, EvidenceType.ESTIMATED}:
            raise ValueError("deep source metrics must be observed or estimated")
        return value


class CapabilityStatus(StrEnum):
    READY = "ready"
    LIMITED = "limited"
    BLOCKED = "blocked"


class CapabilityAssessment(StrictModel):
    capability_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: CapabilityStatus
    required_source_roles: list[SourceRole] = Field(min_length=1)
    satisfied_source_roles: list[SourceRole]
    evidence_refs: list[str]
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def aligned_status(self) -> CapabilityAssessment:
        required = set(self.required_source_roles)
        satisfied = set(self.satisfied_source_roles)
        if not satisfied <= required:
            raise ValueError("capability satisfied roles must be a subset of required roles")
        if self.status is CapabilityStatus.READY and satisfied != required:
            raise ValueError("ready capability must satisfy every required source role")
        if self.status is CapabilityStatus.BLOCKED and satisfied == required:
            raise ValueError("blocked capability cannot satisfy every required source role")
        if bool(self.evidence_refs) != bool(satisfied):
            raise ValueError("capability evidence references must match satisfied roles")
        return self


class ScenarioArtifactRef(StrictModel):
    kind: Literal[
        "policy-scenario",
        "forecast-run",
        "simulation-run",
        "optimization-run",
        "uncertainty-run",
        "decision-pack",
        "decision-brief",
    ]
    path: str = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    evidence_type: EvidenceType

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("scenario artifact paths must be safe relative POSIX paths")
        return value


class DeepScenarioPack(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    pack_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_template_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    created_at: datetime
    data_cutoff: datetime
    status: DeepScenarioStatus
    readiness: ReadinessLevel
    scenario: PolicyScenario
    source_refs: list[str] = Field(min_length=1)
    observed_request_count: int = Field(ge=0)
    observed_feature_summary: dict[str, JsonValue] = Field(min_length=1)
    analytical_artifacts: list[ScenarioArtifactRef] = Field(min_length=2)
    forecast: ForecastRun | None = None
    simulation: SimulationRun | None = None
    optimization: PortfolioOptimizationRun | None = None
    uncertainty: UncertaintyRun | None = None
    decision_pack: DecisionPack
    decision_brief: str = Field(min_length=1)
    assumption_register: list[str] = Field(min_length=1)
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at", "data_cutoff")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "deep-scenario datetime")

    @model_validator(mode="after")
    def scenario_pack_integrity(self) -> DeepScenarioPack:
        if self.scenario.scenario_id != self.pack_id or self.scenario.city_id != self.city_id:
            raise ValueError("deep scenario pack identity must match its PolicyScenario")
        if self.scenario.data_cutoff != self.data_cutoff:
            raise ValueError("deep scenario pack cutoff must match its PolicyScenario")
        if self.decision_pack.scenario_id != self.pack_id:
            raise ValueError("deep scenario pack must embed its matching DecisionPack")
        kinds = [item.kind for item in self.analytical_artifacts]
        if len(kinds) != len(set(kinds)):
            raise ValueError("deep scenario artifact kinds must be unique")
        required_kinds = {"policy-scenario", "decision-pack", "decision-brief"}
        if not required_kinds <= set(kinds):
            raise ValueError("deep scenario pack lacks a required scenario/release artifact")
        model_kind_map = {
            "forecast-run": self.forecast,
            "simulation-run": self.simulation,
            "optimization-run": self.optimization,
            "uncertainty-run": self.uncertainty,
        }
        for kind, model in model_kind_map.items():
            if (kind in kinds) != (model is not None):
                raise ValueError(f"deep scenario {kind} reference and model must align")
        if self.status is DeepScenarioStatus.COMPLETED:
            if self.readiness is not ReadinessLevel.PLANNING_SUPPORT:
                raise ValueError("completed deep scenarios are planning-support outputs")
            if self.decision_pack.status.value != "completed":
                raise ValueError("completed deep scenarios require a completed DecisionPack")
            if self.observed_request_count < 1:
                raise ValueError("completed deep scenarios require observed municipal requests")
            if self.optimization is None or self.uncertainty is None:
                raise ValueError("completed deep scenarios require optimization and uncertainty")
        else:
            if self.readiness is not ReadinessLevel.INSUFFICIENT_EVIDENCE:
                raise ValueError("negative deep scenarios must declare insufficient readiness")
            if self.decision_pack.status.value == "completed":
                raise ValueError("negative deep scenarios cannot embed a completed DecisionPack")
        return self

    def content_hash(self) -> str:
        return tier_d_content_hash(self)


class DeepCityBundle(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    reference_period_start: date
    reference_period_end_exclusive: date
    adapter: CityAdapterManifest
    source_manifests: list[SourceManifest] = Field(min_length=4)
    source_bindings: list[DeepSourceBinding] = Field(min_length=4)
    quality_report: DataQualityReport
    metrics: list[DeepMetric] = Field(min_length=8)
    capabilities: list[CapabilityAssessment] = Field(min_length=7)
    scenario_packs: list[DeepScenarioPack] = Field(min_length=12, max_length=12)
    selection_rationale: list[str] = Field(min_length=2)
    data_gaps: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "deep-city bundle created_at")

    @model_validator(mode="after")
    def deep_bundle_integrity(self) -> DeepCityBundle:
        if self.adapter.tier is not CityTier.DEEP:
            raise ValueError("deep city bundle requires a Tier-D adapter")
        if self.reference_period_start >= self.reference_period_end_exclusive:
            raise ValueError("deep city reference period must be ordered")
        manifests = {item.artifact_id: item for item in self.source_manifests}
        bindings = {item.artifact_id: item for item in self.source_bindings}
        if len(manifests) != len(self.source_manifests):
            raise ValueError("deep city source manifest identifiers must be unique")
        if set(manifests) != set(bindings):
            raise ValueError("deep city source bindings must cover each manifest exactly")
        for artifact_id, binding in bindings.items():
            manifest = manifests[artifact_id]
            if (
                binding.source_id != manifest.source_id
                or binding.content_hash != manifest.content_hash
            ):
                raise ValueError("deep city source binding does not match its manifest")
        if set(self.adapter.source_ids) != {item.source_id for item in self.source_manifests}:
            raise ValueError("deep city adapter source IDs must match embedded manifests")
        roles = {item.role for item in self.source_bindings}
        required_roles = {
            SourceRole.MUNICIPAL_DEMAND,
            SourceRole.CLIMATE_CONTEXT,
            SourceRole.GEOGRAPHIC_IDENTITY,
            SourceRole.DEMOGRAPHIC_CONTEXT,
        }
        if not required_roles <= roles:
            raise ValueError("deep city bundle lacks a required source role")
        if self.quality_report.overall_status is QualityStatus.FAIL:
            raise ValueError("deep city bundle cannot pass with a failed quality report")
        metric_ids = [item.id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("deep city metric identifiers must be unique")
        known_artifacts = set(manifests)
        if any(not set(item.source_refs) <= known_artifacts for item in self.metrics):
            raise ValueError("deep metric references an undeclared source artifact")
        capability_ids = [item.capability_id for item in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("deep city capability identifiers must be unique")
        if len(self.scenario_packs) != 12:
            raise ValueError("deep city bundle requires exactly twelve scenario packs")
        pack_ids = [item.pack_id for item in self.scenario_packs]
        templates = [item.scenario_template_id for item in self.scenario_packs]
        if len(pack_ids) != len(set(pack_ids)) or len(templates) != len(set(templates)):
            raise ValueError("deep city scenario packs and templates must be unique")
        if any(item.city_id != self.adapter.city_id for item in self.scenario_packs):
            raise ValueError("deep scenario city must match its bundle")
        suites = {item.suite for item in self.scenario_packs}
        if suites != set(ApplicationSuite):
            raise ValueError("deep city scenarios must cover all seven application suites")
        observed_counts = {
            item.observed_request_count
            for item in self.scenario_packs
            if item.status is DeepScenarioStatus.COMPLETED
        }
        if not observed_counts:
            raise ValueError("deep city bundle requires at least one completed local-data scenario")
        return self

    def content_hash(self) -> str:
        return tier_d_content_hash(self)


class TierDRegistryEntry(StrictModel):
    selection_order: int = Field(ge=1)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    bundle_ref: str = Field(min_length=1)
    bundle_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    scenario_pack_refs: list[str] = Field(min_length=12, max_length=12)
    scenario_pack_hashes: list[str] = Field(min_length=12, max_length=12)
    completed_scenarios: int = Field(ge=0, le=12)
    negative_scenarios: int = Field(ge=0, le=12)
    underlying_request_count: int = Field(ge=1)
    quality_status: QualityStatus

    @model_validator(mode="after")
    def entry_integrity(self) -> TierDRegistryEntry:
        if len(self.scenario_pack_refs) != len(set(self.scenario_pack_refs)):
            raise ValueError("Tier-D scenario-pack references must be unique")
        if len(self.scenario_pack_hashes) != len(self.scenario_pack_refs):
            raise ValueError("Tier-D scenario-pack references and hashes must align")
        if self.completed_scenarios + self.negative_scenarios != 12:
            raise ValueError("Tier-D scenario outcome counts must total twelve")
        expected = f"cities/{self.city_id}/bundle.json"
        if self.bundle_ref != expected:
            raise ValueError("Tier-D bundle reference must match the city ID")
        for reference in [self.bundle_ref, *self.scenario_pack_refs]:
            path = PurePosixPath(reference)
            if path.is_absolute() or ".." in path.parts or "\\" in reference:
                raise ValueError("Tier-D artifact references must be safe relative paths")
        return self


class TierDRegistry(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    reference_period_start: date
    reference_period_end_exclusive: date
    target_city_count: Literal[8] = 8
    required_scenarios_per_city: Literal[12] = 12
    selection_method: str = Field(min_length=1)
    scenario_templates: list[DeepScenarioTemplate] = Field(min_length=12, max_length=12)
    entries: list[TierDRegistryEntry] = Field(min_length=8, max_length=8)
    total_scenario_packs: Literal[96] = 96
    total_underlying_requests: int = Field(ge=1)
    platform_counts: dict[str, int] = Field(min_length=3)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "Tier-D registry created_at")

    @model_validator(mode="after")
    def registry_integrity(self) -> TierDRegistry:
        if self.reference_period_start >= self.reference_period_end_exclusive:
            raise ValueError("Tier-D reference period must be ordered")
        if len(self.entries) != 8:
            raise ValueError("Tier-D registry requires exactly eight cities")
        if [item.selection_order for item in self.entries] != list(range(1, 9)):
            raise ValueError("Tier-D selection order must be contiguous")
        ids = [item.city_id for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Tier-D city IDs must be unique")
        if sum(len(item.scenario_pack_refs) for item in self.entries) != 96:
            raise ValueError("Tier-D registry must reference exactly 96 scenario packs")
        template_orders = [item.template_order for item in self.scenario_templates]
        template_ids = [item.template_id for item in self.scenario_templates]
        if template_orders != list(range(1, 13)):
            raise ValueError("Tier-D scenario-template order must be contiguous")
        if len(template_ids) != len(set(template_ids)):
            raise ValueError("Tier-D scenario-template identifiers must be unique")
        if self.total_underlying_requests != sum(
            item.underlying_request_count for item in self.entries
        ):
            raise ValueError("Tier-D underlying request total must reconcile to entries")
        expected_platforms: dict[str, int] = {}
        for item in self.entries:
            expected_platforms[item.platform] = expected_platforms.get(item.platform, 0) + 1
        if self.platform_counts != dict(sorted(expected_platforms.items())):
            raise ValueError("Tier-D platform counts must reconcile to entries")
        return self

    def content_hash(self) -> str:
        return tier_d_content_hash(self)


class TierDScenarioEvidence(StrictModel):
    pack_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_template_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    status: DeepScenarioStatus
    observed_request_count: int = Field(ge=0)
    artifact_hashes: dict[str, str] = Field(min_length=3)
    pack_file_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    forecast_input_observations: int = Field(ge=0)
    simulation_iterations: int = Field(ge=0)
    optimization_search_space: int = Field(ge=0)
    optimization_evaluated_plans: int = Field(ge=0)
    optimization_feasible_plans: int = Field(ge=0)
    uncertainty_option_draw_values: int = Field(ge=0)

    @model_validator(mode="after")
    def evidence_integrity(self) -> TierDScenarioEvidence:
        if any(
            not re.fullmatch(SHA256_VALUE_PATTERN, value) for value in self.artifact_hashes.values()
        ):
            raise ValueError("Tier-D scenario artifact hashes must be SHA-256 values")
        if self.optimization_evaluated_plans > self.optimization_search_space:
            raise ValueError("Tier-D optimization evidence exceeds its search space")
        if self.optimization_feasible_plans > self.optimization_evaluated_plans:
            raise ValueError("Tier-D feasible plans exceed evaluated plans")
        work = (
            self.forecast_input_observations,
            self.simulation_iterations,
            self.optimization_search_space,
            self.optimization_evaluated_plans,
            self.uncertainty_option_draw_values,
        )
        if self.status is DeepScenarioStatus.COMPLETED and any(value == 0 for value in work):
            raise ValueError("completed Tier-D evidence must record every analytical workload")
        if self.status is not DeepScenarioStatus.COMPLETED and any(work):
            raise ValueError("negative Tier-D evidence cannot claim completed analytical workload")
        return self


class TierDEvidenceSummary(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    summary_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    source_artifact_hashes: dict[str, str] = Field(min_length=49, max_length=49)
    distinct_source_datasets: Literal[11] = 11
    source_manifest_artifacts: Literal[49] = 49
    aggregate_source_rows: int = Field(ge=1)
    context_source_units: int = Field(ge=1)
    deduplicated_underlying_requests: int = Field(ge=1)
    nonduplicative_scenario_designs: Literal[12] = 12
    city_bound_scenario_executions: Literal[96] = 96
    scenarios: list[TierDScenarioEvidence] = Field(min_length=96, max_length=96)
    completed_scenarios: int = Field(ge=1, le=96)
    negative_scenarios: int = Field(ge=1, le=96)
    forecast_runs: int = Field(ge=1)
    total_forecast_input_observations: int = Field(ge=1)
    simulation_runs: int = Field(ge=1)
    total_simulation_iterations: int = Field(ge=1)
    optimization_tasks: int = Field(ge=1)
    total_optimization_search_space: int = Field(ge=1)
    total_optimization_evaluated_plans: int = Field(ge=1)
    total_optimization_feasible_plans: int = Field(ge=1)
    uncertainty_runs: int = Field(ge=1)
    total_uncertainty_option_draw_values: int = Field(ge=1)
    decision_packs: Literal[96] = 96
    decision_briefs: Literal[96] = 96
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "Tier-D evidence-summary created_at")

    @model_validator(mode="after")
    def summary_integrity(self) -> TierDEvidenceSummary:
        if any(
            not re.fullmatch(SHA256_VALUE_PATTERN, value)
            for value in self.source_artifact_hashes.values()
        ):
            raise ValueError("Tier-D source-artifact hashes must be SHA-256 values")
        pack_ids = [item.pack_id for item in self.scenarios]
        if len(pack_ids) != len(set(pack_ids)):
            raise ValueError("Tier-D evidence scenario-pack identifiers must be unique")
        expected = {
            "completed_scenarios": sum(
                item.status is DeepScenarioStatus.COMPLETED for item in self.scenarios
            ),
            "negative_scenarios": sum(
                item.status is not DeepScenarioStatus.COMPLETED for item in self.scenarios
            ),
            "forecast_runs": sum(item.forecast_input_observations > 0 for item in self.scenarios),
            "total_forecast_input_observations": sum(
                item.forecast_input_observations for item in self.scenarios
            ),
            "simulation_runs": sum(item.simulation_iterations > 0 for item in self.scenarios),
            "total_simulation_iterations": sum(
                item.simulation_iterations for item in self.scenarios
            ),
            "optimization_tasks": sum(
                item.optimization_search_space > 0 for item in self.scenarios
            ),
            "total_optimization_search_space": sum(
                item.optimization_search_space for item in self.scenarios
            ),
            "total_optimization_evaluated_plans": sum(
                item.optimization_evaluated_plans for item in self.scenarios
            ),
            "total_optimization_feasible_plans": sum(
                item.optimization_feasible_plans for item in self.scenarios
            ),
            "uncertainty_runs": sum(
                item.uncertainty_option_draw_values > 0 for item in self.scenarios
            ),
            "total_uncertainty_option_draw_values": sum(
                item.uncertainty_option_draw_values for item in self.scenarios
            ),
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise ValueError(f"Tier-D evidence-summary field does not reconcile: {field}")
        if self.completed_scenarios + self.negative_scenarios != 96:
            raise ValueError("Tier-D evidence scenario statuses must total 96")
        return self


__all__ = [
    "ApplicationSuite",
    "CapabilityAssessment",
    "CapabilityStatus",
    "DeepCityBundle",
    "DeepMetric",
    "DeepScenarioPack",
    "DeepScenarioStatus",
    "DeepScenarioTemplate",
    "DeepSourceBinding",
    "ReadinessLevel",
    "ScenarioArtifactRef",
    "ScenarioCompletionStrategy",
    "SourceRole",
    "TierDEvidenceSummary",
    "TierDRegistry",
    "TierDRegistryEntry",
    "TierDScenarioEvidence",
]
