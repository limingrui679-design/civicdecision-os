"""Strict contracts for standardized city evidence and non-decision screening runs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    JsonValue,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
)
from civicdecision.protocols.city import CityAdapterManifest, CityTier
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.city_catalog import GlobalCityCatalogEntry

SHA256_VALUE_PATTERN = r"^sha256:[0-9a-f]{64}$"


class GeographicAlignment(StrEnum):
    IDENTITY_POINT = "identity-point"
    GRIDDED_POINT = "gridded-point"
    COUNTRY_CONTEXT = "country-context"


class QualityStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ScenarioScreenStatus(StrEnum):
    SCREENED = "screened"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"
    FAILED = "failed"


class DecisionReadiness(StrEnum):
    DESCRIPTIVE_ONLY = "descriptive-only"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class SourceBinding(StrictModel):
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    alignment: GeographicAlignment
    role: str = Field(min_length=1)
    geographic_scope: str = Field(min_length=1)
    temporal_scope: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class QualityCheck(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: QualityStatus
    measured: JsonValue
    expected: JsonValue
    details: str = Field(min_length=1)


class DataQualityReport(StrictModel):
    overall_status: QualityStatus
    completeness_rate: float = Field(ge=0, le=1)
    missing_values: int = Field(ge=0)
    checks: list[QualityCheck] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def status_matches_checks(self) -> DataQualityReport:
        check_ids = [item.id for item in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("quality check ids must be unique")
        statuses = {item.status for item in self.checks}
        expected = (
            QualityStatus.FAIL
            if QualityStatus.FAIL in statuses
            else QualityStatus.WARN
            if QualityStatus.WARN in statuses
            else QualityStatus.PASS
        )
        if self.overall_status is not expected:
            raise ValueError("overall quality status does not match check results")
        return self


class StandardMetric(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    value: float | int | None
    unit: str = Field(min_length=1)
    evidence_type: EvidenceType
    geographic_scope: str = Field(min_length=1)
    temporal_scope: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    method: str | None = None
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_refs")
    @classmethod
    def unique_source_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("metric source references must be unique")
        return value

    @model_validator(mode="after")
    def metric_evidence_gate(self) -> StandardMetric:
        if self.evidence_type not in {EvidenceType.OBSERVED, EvidenceType.ESTIMATED}:
            raise ValueError("standard metrics must be observed or estimated")
        if self.evidence_type is EvidenceType.ESTIMATED and not self.method:
            raise ValueError("estimated standard metrics require a method")
        return self


class StandardScenarioRun(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_id: str = Field(pattern=IDENTIFIER_PATTERN)
    template_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1)
    status: ScenarioScreenStatus
    analysis_mode: Literal["descriptive"] = "descriptive"
    decision_readiness: DecisionReadiness
    recommendation_issued: Literal[False] = False
    source_refs: list[str] = Field(min_length=1)
    metrics: list[StandardMetric] = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    proposed_follow_up: list[str] = Field(min_length=1)
    required_next_evidence: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "standard scenario run created_at")

    @field_validator("source_refs")
    @classmethod
    def unique_run_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("scenario source references must be unique")
        return value

    @model_validator(mode="after")
    def non_decision_gate(self) -> StandardScenarioRun:
        metric_ids = [item.id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("scenario metric ids must be unique")
        allowed_sources = set(self.source_refs)
        if any(not set(item.source_refs) <= allowed_sources for item in self.metrics):
            raise ValueError("scenario metric source is not declared by the run")
        if (
            self.status is ScenarioScreenStatus.SCREENED
            and self.decision_readiness is not DecisionReadiness.DESCRIPTIVE_ONLY
        ):
            raise ValueError("screened runs must remain descriptive-only")
        if (
            self.status is not ScenarioScreenStatus.SCREENED
            and self.decision_readiness is not DecisionReadiness.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError("negative screening runs must declare insufficient evidence")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class StandardizedCityBundle(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    adapter: CityAdapterManifest
    catalog_entry: GlobalCityCatalogEntry
    source_manifests: list[SourceManifest] = Field(min_length=3)
    source_bindings: list[SourceBinding] = Field(min_length=3)
    quality_report: DataQualityReport
    metrics: list[StandardMetric] = Field(min_length=1)
    scenario_runs: list[StandardScenarioRun] = Field(min_length=3)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "standardized city bundle created_at")

    @model_validator(mode="after")
    def standardized_integrity(self) -> StandardizedCityBundle:
        if self.adapter.tier is not CityTier.STANDARDIZED:
            raise ValueError("standardized bundles require a Tier-S adapter")
        if self.adapter.city_id != self.catalog_entry.city_id:
            raise ValueError("adapter and catalog city identifiers must match")
        manifests = {item.artifact_id: item for item in self.source_manifests}
        if len(manifests) != len(self.source_manifests):
            raise ValueError("source manifest artifact identifiers must be unique")
        bindings = {item.artifact_id: item for item in self.source_bindings}
        if len(bindings) != len(self.source_bindings):
            raise ValueError("source binding artifact identifiers must be unique")
        if set(bindings) != set(manifests):
            raise ValueError("source bindings must cover every source manifest exactly")
        for artifact_id, binding in bindings.items():
            manifest = manifests[artifact_id]
            if (
                binding.source_id != manifest.source_id
                or binding.content_hash != manifest.content_hash
            ):
                raise ValueError("source binding does not match its source manifest")
        if set(self.adapter.source_ids) != {item.source_id for item in self.source_manifests}:
            raise ValueError("adapter source ids must match bundle source families")
        alignments = {item.alignment for item in self.source_bindings}
        required_alignments = {
            GeographicAlignment.IDENTITY_POINT,
            GeographicAlignment.GRIDDED_POINT,
            GeographicAlignment.COUNTRY_CONTEXT,
        }
        if not required_alignments <= alignments:
            raise ValueError("Tier-S bundle lacks a required geographic alignment layer")
        if self.quality_report.overall_status is QualityStatus.FAIL:
            raise ValueError("Tier-S bundle cannot contain failed required quality checks")
        if self.quality_report.completeness_rate != 1:
            raise ValueError("Tier-S required fields must be complete")
        metric_ids = [item.id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("bundle metric ids must be unique")
        source_ids = set(manifests)
        if any(not set(item.source_refs) <= source_ids for item in self.metrics):
            raise ValueError("bundle metric source is not declared")
        run_ids = [item.run_id for item in self.scenario_runs]
        scenario_ids = [item.scenario_id for item in self.scenario_runs]
        template_ids = [item.template_id for item in self.scenario_runs]
        if len(run_ids) != len(set(run_ids)) or len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("standard scenario run identifiers must be unique")
        if len(template_ids) != len(set(template_ids)):
            raise ValueError("standard scenario templates must be non-duplicative per city")
        if any(item.city_id != self.adapter.city_id for item in self.scenario_runs):
            raise ValueError("scenario run city does not match its bundle")
        known_metrics = set(metric_ids)
        if any(
            metric.id not in known_metrics for run in self.scenario_runs for metric in run.metrics
        ):
            raise ValueError("scenario run contains an undeclared bundle metric")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class TierSRegistryEntry(StrictModel):
    selection_order: int = Field(ge=1)
    tier_g_rank: int = Field(ge=1)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    bundle_ref: str = Field(min_length=1)
    bundle_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    run_refs: list[str] = Field(min_length=3)
    run_hashes: list[str] = Field(min_length=3)
    scenario_statuses: list[ScenarioScreenStatus] = Field(min_length=3)
    quality_status: QualityStatus

    @model_validator(mode="after")
    def registry_entry_integrity(self) -> TierSRegistryEntry:
        if not (len(self.run_refs) == len(self.run_hashes) == len(self.scenario_statuses)):
            raise ValueError("registry run references, hashes, and statuses must align")
        if len(self.run_refs) != len(set(self.run_refs)):
            raise ValueError("registry run references must be unique")
        expected_bundle = f"cities/{self.city_id}/bundle.json"
        if self.bundle_ref != expected_bundle:
            raise ValueError("registry bundle reference must match the city identifier")
        for reference in [self.bundle_ref, *self.run_refs]:
            path = PurePosixPath(reference)
            if path.is_absolute() or ".." in path.parts or "\\" in reference:
                raise ValueError("registry artifact references must be safe relative POSIX paths")
        if any(
            not reference.startswith("runs/") or not reference.endswith(".json")
            for reference in self.run_refs
        ):
            raise ValueError("registry run references must use runs/<run-id>.json")
        if len(self.run_hashes) != len(set(self.run_hashes)):
            raise ValueError("registry run hashes must be unique")
        return self


class TierSExclusionRecord(StrictModel):
    tier_g_rank: int = Field(ge=1)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    reasons: list[str] = Field(min_length=1)

    @field_validator("reasons")
    @classmethod
    def unique_reasons(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Tier-S exclusion reasons must be unique")
        return value


class TierSRegistry(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    target_count: int = Field(ge=1)
    selection_method: str = Field(min_length=1)
    reference_climate_year: int = Field(ge=1981, le=2100)
    reference_context_year: int = Field(ge=1960, le=2100)
    required_climate_parameters: list[str] = Field(min_length=1)
    required_country_indicators: list[str] = Field(min_length=1)
    entries: list[TierSRegistryEntry] = Field(min_length=1)
    exclusions_before_target: list[TierSExclusionRecord] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "Tier-S registry created_at")

    @model_validator(mode="after")
    def registry_integrity(self) -> TierSRegistry:
        if len(self.entries) != self.target_count:
            raise ValueError("Tier-S registry entries must match target_count")
        if [item.selection_order for item in self.entries] != list(range(1, self.target_count + 1)):
            raise ValueError("Tier-S selection order must be contiguous")
        ids = [item.city_id for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Tier-S city identifiers must be unique")
        excluded_ids = [item.city_id for item in self.exclusions_before_target]
        excluded_ranks = [item.tier_g_rank for item in self.exclusions_before_target]
        if len(excluded_ids) != len(set(excluded_ids)) or len(excluded_ranks) != len(
            set(excluded_ranks)
        ):
            raise ValueError("Tier-S exclusion identifiers and ranks must be unique")
        if set(ids) & set(excluded_ids):
            raise ValueError("Tier-S cities cannot be both selected and excluded")
        if excluded_ranks and max(excluded_ranks) > max(item.tier_g_rank for item in self.entries):
            raise ValueError("Tier-S exclusions must precede completion of the target")
        if len(self.required_climate_parameters) != len(set(self.required_climate_parameters)):
            raise ValueError("required climate parameters must be unique")
        if len(self.required_country_indicators) != len(set(self.required_country_indicators)):
            raise ValueError("required country indicators must be unique")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))
