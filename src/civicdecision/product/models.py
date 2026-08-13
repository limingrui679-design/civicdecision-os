"""Stable projection models for every CivicDecision product surface."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import IDENTIFIER_PATTERN, JsonValue, StrictModel, ensure_aware
from civicdecision.protocols.evidence import EvidenceType


class ProductTier(StrEnum):
    GLOBAL = "G"
    STANDARDIZED = "S"
    DEEP = "D"


class ScenarioKind(StrEnum):
    STANDARD_SCREEN = "standard-screen"
    DEEP_PACK = "deep-pack"
    REFERENCE_PACK = "reference-pack"


class ScenarioStatus(StrEnum):
    COMPLETED = "completed"
    SCREENED = "screened"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"
    INFEASIBLE = "infeasible"


class ProductHealth(StrictModel):
    status: Literal["ok", "not-ready"]
    version: str = Field(min_length=1)
    catalog_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    checked_at: datetime

    @field_validator("checked_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "product health checked_at")


class CatalogSummary(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    software_version: str = Field(min_length=1)
    catalog_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generated_from_latest_source_at: datetime
    tier_g_cities: int = Field(ge=0)
    tier_s_cities: int = Field(ge=0)
    tier_d_cities: int = Field(ge=0)
    exposed_city_records: int = Field(ge=0)
    tier_assignments: int = Field(ge=0)
    source_artifacts: int = Field(ge=0)
    declared_source_units: int = Field(ge=0)
    standard_scenario_screens: int = Field(ge=0)
    nonduplicative_deep_designs: int = Field(ge=0)
    deep_scenario_executions: int = Field(ge=0)
    completed_deep_executions: int = Field(ge=0)
    negative_deep_executions: int = Field(ge=0)
    decision_packs: int = Field(ge=0)
    completed_decision_packs: int = Field(ge=0)
    negative_decision_packs: int = Field(ge=0)
    benchmark_run_artifacts: int = Field(ge=0)
    historical_replays: int = Field(ge=0)
    optimization_benchmarks: int = Field(ge=0)
    claim_boundary: list[str] = Field(min_length=1)

    @field_validator("generated_from_latest_source_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "catalog summary source timestamp")

    @model_validator(mode="after")
    def totals_reconcile(self) -> CatalogSummary:
        if self.tier_assignments != self.tier_g_cities + self.tier_s_cities + self.tier_d_cities:
            raise ValueError("catalog tier assignments must reconcile")
        if self.deep_scenario_executions != (
            self.completed_deep_executions + self.negative_deep_executions
        ):
            raise ValueError("deep scenario status counts must reconcile")
        if self.decision_packs != self.completed_decision_packs + self.negative_decision_packs:
            raise ValueError("DecisionPack status counts must reconcile")
        return self


class Pagination(StrictModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def page_integrity(self) -> Pagination:
        expected = min(self.limit, max(0, self.total - self.offset))
        if self.returned != expected:
            raise ValueError("pagination returned count does not match total/limit/offset")
        expected_next = (
            self.offset + self.returned if self.offset + self.returned < self.total else None
        )
        if self.next_offset != expected_next:
            raise ValueError("pagination next offset does not reconcile")
        return self


class CitySummary(StrictModel):
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    tier: ProductTier
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1)
    source_population: int | None = Field(default=None, ge=0)
    quality_status: str | None = None
    source_artifact_count: int = Field(ge=0)
    scenario_count: int = Field(ge=0)
    completed_scenarios: int = Field(ge=0)
    negative_scenarios: int = Field(ge=0)
    readiness: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def scenario_counts_reconcile(self) -> CitySummary:
        if self.completed_scenarios + self.negative_scenarios > self.scenario_count:
            raise ValueError("city scenario status counts exceed scenario count")
        return self


class CityPage(StrictModel):
    pagination: Pagination
    items: list[CitySummary]

    @model_validator(mode="after")
    def count_matches(self) -> CityPage:
        if len(self.items) != self.pagination.returned:
            raise ValueError("city page item count must match pagination")
        return self


class MetricView(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    value: int | float | str | None
    unit: str = Field(min_length=1)
    evidence_type: EvidenceType
    method: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class CapabilityView(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: str = Field(min_length=1)
    diagnostics: list[str] = Field(min_length=1)
    evidence_refs: list[str]
    limitations: list[str] = Field(min_length=1)


class CityDetail(StrictModel):
    city: CitySummary
    source_ids: list[str] = Field(min_length=1)
    source_artifact_ids: list[str] = Field(min_length=1)
    metrics: list[MetricView]
    capabilities: list[CapabilityView]
    quality_checks: dict[str, str]
    data_gaps: list[str]
    provenance: dict[str, JsonValue] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_ids", "source_artifact_ids")
    @classmethod
    def sorted_unique(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("city detail source identifiers must be sorted and unique")
        return value


class ScenarioSummary(StrictModel):
    execution_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_id: str = Field(pattern=IDENTIFIER_PATTERN)
    template_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    kind: ScenarioKind
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_name: str = Field(min_length=1)
    suite: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: ScenarioStatus
    readiness: str = Field(min_length=1)
    recommendation_issued: bool
    selected_option_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    observed_request_count: int | None = Field(default=None, ge=0)
    source_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    analysis_modes: list[str]
    evidence_types: list[EvidenceType]
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def recommendation_boundary(self) -> ScenarioSummary:
        if self.recommendation_issued != (self.selected_option_id is not None):
            raise ValueError("scenario recommendation flag must match selected option")
        if self.kind is ScenarioKind.STANDARD_SCREEN and self.recommendation_issued:
            raise ValueError("standard screens cannot issue recommendations")
        return self


class ScenarioPage(StrictModel):
    pagination: Pagination
    items: list[ScenarioSummary]

    @model_validator(mode="after")
    def count_matches(self) -> ScenarioPage:
        if len(self.items) != self.pagination.returned:
            raise ValueError("scenario page item count must match pagination")
        return self


class SourceSummary(StrictModel):
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    license: str = Field(min_length=1)
    retrieved_at: datetime
    record_count: int = Field(ge=0)
    geographic_scope: str = Field(min_length=1)
    temporal_scope: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    limitations: list[str] = Field(min_length=1)

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "source summary retrieved_at")


class SourcePage(StrictModel):
    pagination: Pagination
    items: list[SourceSummary]

    @model_validator(mode="after")
    def count_matches(self) -> SourcePage:
        if len(self.items) != self.pagination.returned:
            raise ValueError("source page item count must match pagination")
        return self


class ScenarioDetail(StrictModel):
    scenario: ScenarioSummary
    payload_schema: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(min_length=1)
    artifact_hashes: dict[str, str]
    claim_boundary: list[str] = Field(min_length=1)

    @field_validator("artifact_hashes")
    @classmethod
    def valid_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not item.startswith("sha256:") or len(item) != 71 for item in value.values()):
            raise ValueError("scenario artifact hashes must be SHA-256 values")
        return value


class SuiteOverview(StrictModel):
    suite: str = Field(min_length=1)
    template_count: int = Field(ge=0)
    execution_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    cities: int = Field(ge=0)
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def counts_reconcile(self) -> SuiteOverview:
        if self.execution_count != self.completed_count + self.negative_count:
            raise ValueError("suite execution statuses must reconcile")
        return self


class BenchmarkOverview(StrictModel):
    summary_id: str = Field(pattern=IDENTIFIER_PATTERN)
    artifact_set_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    run_artifacts: int = Field(ge=0)
    historical_replays: int = Field(ge=0)
    replay_training_values: int = Field(ge=0)
    replay_holdout_values: int = Field(ge=0)
    optimization_tasks: int = Field(ge=0)
    optimization_search_space: int = Field(ge=0)
    optimization_evaluated_plans: int = Field(ge=0)
    optimization_feasible_plans: int = Field(ge=0)
    engine_qualification_runs: int = Field(ge=0)
    status_counts: dict[str, int]
    method_counts: dict[str, int]
    limitations: list[str] = Field(min_length=1)


__all__ = [
    "BenchmarkOverview",
    "CapabilityView",
    "CatalogSummary",
    "CityDetail",
    "CityPage",
    "CitySummary",
    "MetricView",
    "Pagination",
    "ProductHealth",
    "ProductTier",
    "ScenarioDetail",
    "ScenarioKind",
    "ScenarioPage",
    "ScenarioStatus",
    "ScenarioSummary",
    "SourcePage",
    "SourceSummary",
    "SuiteOverview",
]
