"""Strict contracts for the non-duplicative scenario design library."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from civicdecision.deep.models import ApplicationSuite
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.scenario import AnalysisMode

SHA256_VALUE_PATTERN = r"^sha256:[0-9a-f]{64}$"


def _safe_relative_posix_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("scenario library artifact paths must be safe relative POSIX paths")
    return value


class DecisionType(StrEnum):
    DIAGNOSE = "diagnose"
    FORECAST = "forecast"
    PRIORITIZE = "prioritize"
    SITE = "site"
    ALLOCATE = "allocate"
    SCHEDULE = "schedule"
    STRESS_TEST = "stress-test"
    EVALUATE = "evaluate"


class DecisionHorizon(StrEnum):
    REAL_TIME = "real-time"
    DAYS = "days"
    WEEKS = "weeks"
    SEASONAL = "seasonal"
    ANNUAL = "annual"
    MULTI_YEAR = "multi-year"


class SpatialUnit(StrEnum):
    FACILITY = "facility"
    ASSET = "asset"
    PARCEL = "parcel"
    CORRIDOR = "corridor"
    NETWORK = "network"
    SERVICE_AREA = "service-area"
    NEIGHBORHOOD = "neighborhood"
    CITYWIDE = "citywide"
    POPULATION_GROUP = "population-group"


class DesignConstraintKind(StrEnum):
    BUDGET = "budget"
    CAPACITY = "capacity"
    EQUITY = "equity"
    RISK = "risk"
    TIME = "time"
    REGULATORY = "regulatory"
    TECHNICAL = "technical"
    ENVIRONMENTAL = "environmental"


class EvidenceGateType(StrEnum):
    COMPLETENESS = "data-completeness"
    LINEAGE = "source-lineage"
    TEMPORAL_ALIGNMENT = "temporal-alignment"
    GEOGRAPHIC_ALIGNMENT = "geographic-alignment"
    NETWORK_READINESS = "network-readiness"
    IDENTIFICATION = "causal-identification"
    CALIBRATION = "model-calibration"
    COST_CAPACITY = "cost-capacity"
    LEGAL_AUTHORITY = "legal-authority"
    EQUITY_MEASUREMENT = "equity-measurement"
    EXTERNAL_VALIDATION = "external-validation"


class LibrarySourceRole(StrEnum):
    MUNICIPAL_DEMAND = "municipal-demand"
    CLIMATE_HAZARD = "climate-hazard"
    GEOGRAPHIC_IDENTITY = "geographic-identity"
    DEMOGRAPHIC_CONTEXT = "demographic-context"
    TRANSPORT_NETWORK = "transport-network"
    SERVICE_SCHEDULE = "service-schedule"
    FACILITY_INVENTORY = "facility-inventory"
    ASSET_INVENTORY = "asset-inventory"
    ASSET_CONDITION = "asset-condition"
    LAND_PARCEL = "land-parcel"
    HOUSING_MARKET = "housing-market"
    HEALTH_OUTCOME = "health-outcome"
    ENVIRONMENTAL_EXPOSURE = "environmental-exposure"
    FINANCIAL_COST = "financial-cost"
    OPERATING_CAPACITY = "operating-capacity"
    INTERVENTION_ASSIGNMENT = "intervention-assignment"
    OUTCOME_PANEL = "outcome-panel"
    EQUITY_ATTRIBUTE = "equity-attribute"
    LEGAL_REGULATORY = "legal-regulatory"
    REAL_TIME_STATE = "real-time-state"
    COMMUNITY_INPUT = "community-input"


class ImplementationStatus(StrEnum):
    REFERENCE_IMPLEMENTED = "reference-implemented"
    DESIGN_ONLY = "design-only"


class CurrentReadiness(StrEnum):
    REFERENCE_IMPLEMENTED = "reference-implemented"
    UNCOMPILED_CURRENT_INPUTS = "uncompiled-current-inputs"
    BLOCKED_SOURCE = "blocked-missing-source"
    BLOCKED_METHOD = "blocked-method"
    BLOCKED_MULTI = "blocked-multiple-gates"


class ScenarioDesignObjective(StrictModel):
    objective_id: str = Field(pattern=IDENTIFIER_PATTERN)
    metric: str = Field(min_length=3)
    sense: Literal["minimize", "maximize"]
    unit: str = Field(min_length=1)
    evidence_type: EvidenceType
    primary: bool = False


class ScenarioDesignConstraint(StrictModel):
    constraint_id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: DesignConstraintKind
    description: str = Field(min_length=8)
    hard: bool = True
    binding: bool = False
    required_source_roles: list[LibrarySourceRole]

    @field_validator("required_source_roles")
    @classmethod
    def unique_roles(cls, value: list[LibrarySourceRole]) -> list[LibrarySourceRole]:
        if len(value) != len(set(value)):
            raise ValueError("constraint source roles must be unique")
        return value


class ScenarioEvidenceGate(StrictModel):
    gate_id: str = Field(pattern=IDENTIFIER_PATTERN)
    gate_type: EvidenceGateType
    pass_condition: str = Field(min_length=12)
    failure_status: Literal["insufficient-evidence"] = "insufficient-evidence"
    failure_release: str = Field(min_length=12)
    required_source_roles: list[LibrarySourceRole] = Field(min_length=1)
    required_evidence_types: list[EvidenceType] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_requirements(self) -> ScenarioEvidenceGate:
        if len(self.required_source_roles) != len(set(self.required_source_roles)):
            raise ValueError("gate source roles must be unique")
        if len(self.required_evidence_types) != len(set(self.required_evidence_types)):
            raise ValueError("gate evidence types must be unique")
        return self


class ScenarioIndependenceKey(StrictModel):
    """Substantive axes used to detect renamed or city-copied designs."""

    decision_object: str = Field(min_length=5)
    intervention_mechanism: str = Field(min_length=5)
    primary_outcome: str = Field(min_length=5)
    binding_constraint: str = Field(min_length=5)
    evidence_gate: str = Field(min_length=5)
    horizon: DecisionHorizon
    spatial_unit: SpatialUnit

    def signature(self) -> str:
        return sha256_bytes(canonical_json(self))


class ScenarioDesign(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_order: int = Field(ge=1, le=240)
    design_id: str = Field(pattern=IDENTIFIER_PATTERN)
    family_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    family_title: str = Field(min_length=3)
    title: str = Field(min_length=5, max_length=180)
    decision_question: str = Field(min_length=12)
    decision_type: DecisionType
    decision_owner: str = Field(min_length=3)
    affected_system: str = Field(min_length=5)
    horizon: DecisionHorizon
    decision_cadence: str = Field(min_length=3)
    spatial_unit: SpatialUnit
    baseline: str = Field(min_length=8)
    alternatives: list[str] = Field(min_length=2)
    objectives: list[ScenarioDesignObjective] = Field(min_length=1)
    constraints: list[ScenarioDesignConstraint] = Field(min_length=1)
    analysis_modes: list[AnalysisMode] = Field(min_length=1)
    evidence_requirements: list[EvidenceType] = Field(min_length=1)
    required_source_roles: list[LibrarySourceRole] = Field(min_length=1)
    release_gate: ScenarioEvidenceGate
    independence_key: ScenarioIndependenceKey
    design_signature: str = Field(pattern=SHA256_VALUE_PATTERN)
    implementation_status: ImplementationStatus
    current_readiness: CurrentReadiness
    existing_template_ref: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    reference_implementation_note: str | None = Field(default=None, min_length=24)
    city_bindings: list[str] = Field(default_factory=list, max_length=0)
    method_claimed: Literal[False] = False
    intended_claim: str = Field(min_length=12)
    prohibited_claims: list[str] = Field(min_length=2)
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=2)
    transportability_risks: list[str] = Field(min_length=1)
    tags: list[str] = Field(min_length=3)

    @model_validator(mode="after")
    def design_integrity(self) -> ScenarioDesign:
        unique_groups = [
            ("alternatives", self.alternatives),
            ("objective ids", [item.objective_id for item in self.objectives]),
            ("constraint ids", [item.constraint_id for item in self.constraints]),
            ("analysis modes", [item.value for item in self.analysis_modes]),
            ("evidence requirements", [item.value for item in self.evidence_requirements]),
            ("source roles", [item.value for item in self.required_source_roles]),
            ("prohibited claims", self.prohibited_claims),
            ("tags", self.tags),
        ]
        for name, values in unique_groups:
            if len(values) != len(set(values)):
                raise ValueError(f"scenario design {name} must be unique")
        if self.tags != sorted(self.tags):
            raise ValueError("scenario design tags must be sorted")
        primary = [item for item in self.objectives if item.primary]
        if len(primary) != 1:
            raise ValueError("scenario design requires exactly one primary objective")
        binding = [item for item in self.constraints if item.binding]
        if len(binding) != 1:
            raise ValueError("scenario design requires exactly one binding constraint")
        if primary[0].metric != self.independence_key.primary_outcome:
            raise ValueError("primary objective must match the independence key")
        if binding[0].description != self.independence_key.binding_constraint:
            raise ValueError("binding constraint must match the independence key")
        if self.release_gate.pass_condition != self.independence_key.evidence_gate:
            raise ValueError("release gate must match the independence key")
        if self.horizon is not self.independence_key.horizon:
            raise ValueError("scenario horizon must match the independence key")
        if self.spatial_unit is not self.independence_key.spatial_unit:
            raise ValueError("scenario spatial unit must match the independence key")
        if self.design_signature != self.independence_key.signature():
            raise ValueError("scenario design signature does not match substantive axes")
        role_set = set(self.required_source_roles)
        if not set(self.release_gate.required_source_roles) <= role_set:
            raise ValueError("release-gate source roles must be declared by the scenario")
        if any(not set(item.required_source_roles) <= role_set for item in self.constraints):
            raise ValueError("constraint source roles must be declared by the scenario")
        if not set(self.release_gate.required_evidence_types) <= set(self.evidence_requirements):
            raise ValueError("release-gate evidence types must be declared by the scenario")
        if AnalysisMode.CAUSAL in self.analysis_modes:
            if EvidenceType.CAUSAL not in self.evidence_requirements:
                raise ValueError("causal design mode requires causal evidence")
            if self.release_gate.gate_type is not EvidenceGateType.IDENTIFICATION:
                raise ValueError("causal design mode requires an identification gate")
        implemented = self.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
        if implemented != (self.existing_template_ref is not None):
            raise ValueError("reference implementation status and template reference must align")
        if implemented != (self.reference_implementation_note is not None):
            raise ValueError("reference implementation status and scope note must align")
        if implemented != (self.current_readiness is CurrentReadiness.REFERENCE_IMPLEMENTED):
            raise ValueError("reference implementation and readiness must align")
        required_tags = {self.suite.value, self.family_id, self.decision_type.value}
        if not required_tags <= set(self.tags):
            raise ValueError("scenario design tags lack suite, family, or decision type")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class ScenarioFamily(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    family_order: int = Field(ge=1, le=30)
    family_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    title: str = Field(min_length=3)
    description: str = Field(min_length=12)
    affected_system: str = Field(min_length=5)
    decision_owner: str = Field(min_length=3)
    design_refs: list[str] = Field(min_length=8, max_length=8)
    decision_types: list[DecisionType] = Field(min_length=8, max_length=8)
    design_signatures: list[str] = Field(min_length=8, max_length=8)
    common_source_roles: list[LibrarySourceRole] = Field(min_length=1)
    claim_boundary: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def family_integrity(self) -> ScenarioFamily:
        if len(self.design_refs) != len(set(self.design_refs)):
            raise ValueError("scenario family design references must be unique")
        if set(self.decision_types) != set(DecisionType):
            raise ValueError("each scenario family must cover all eight decision types")
        if len(self.design_signatures) != len(set(self.design_signatures)):
            raise ValueError("scenario family signatures must be unique")
        if len(self.common_source_roles) != len(set(self.common_source_roles)):
            raise ValueError("scenario family source roles must be unique")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class ScenarioDesignIndexEntry(StrictModel):
    design_order: int = Field(ge=1, le=240)
    design_id: str = Field(pattern=IDENTIFIER_PATTERN)
    family_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    title: str = Field(min_length=5)
    decision_type: DecisionType
    implementation_status: ImplementationStatus
    current_readiness: CurrentReadiness
    existing_template_ref: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    design_signature: str = Field(pattern=SHA256_VALUE_PATTERN)
    artifact_path: str
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)

    @field_validator("artifact_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return _safe_relative_posix_path(value)


class ScenarioFamilyIndexEntry(StrictModel):
    family_order: int = Field(ge=1, le=30)
    family_id: str = Field(pattern=IDENTIFIER_PATTERN)
    suite: ApplicationSuite
    title: str = Field(min_length=3)
    design_count: Literal[8] = 8
    artifact_path: str
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)

    @field_validator("artifact_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return _safe_relative_posix_path(value)


class ScenarioLibraryRegistry(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    published_at: datetime
    design_count: Literal[240] = 240
    family_count: Literal[30] = 30
    city_bound_execution_count: Literal[0] = 0
    method_count_claimed: Literal[0] = 0
    suite_counts: dict[ApplicationSuite, int]
    decision_type_counts: dict[DecisionType, int]
    implementation_status_counts: dict[ImplementationStatus, int]
    current_readiness_counts: dict[CurrentReadiness, int]
    definitions_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    artifact_set_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    designs: list[ScenarioDesignIndexEntry] = Field(min_length=240, max_length=240)
    families: list[ScenarioFamilyIndexEntry] = Field(min_length=30, max_length=30)
    claim_boundary: list[str] = Field(min_length=4)

    @field_validator("published_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "scenario library published_at")

    @model_validator(mode="after")
    def registry_integrity(self) -> ScenarioLibraryRegistry:
        if [item.design_order for item in self.designs] != list(range(1, 241)):
            raise ValueError("scenario design order must be contiguous")
        if [item.family_order for item in self.families] != list(range(1, 31)):
            raise ValueError("scenario family order must be contiguous")
        if len({item.design_id for item in self.designs}) != 240:
            raise ValueError("scenario design identifiers must be unique")
        if len({item.design_signature for item in self.designs}) != 240:
            raise ValueError("scenario substantive signatures must be unique")
        if len({item.family_id for item in self.families}) != 30:
            raise ValueError("scenario family identifiers must be unique")
        if sum(self.suite_counts.values()) != 240 or set(self.suite_counts) != set(
            ApplicationSuite
        ):
            raise ValueError("scenario suite counts must cover 240 designs and all seven suites")
        if set(self.decision_type_counts) != set(DecisionType) or any(
            count != 30 for count in self.decision_type_counts.values()
        ):
            raise ValueError("each decision type must appear once in each of 30 families")
        if sum(self.implementation_status_counts.values()) != 240:
            raise ValueError("scenario implementation status counts must reconcile")
        if sum(self.current_readiness_counts.values()) != 240:
            raise ValueError("scenario readiness counts must reconcile")
        refs = [item.existing_template_ref for item in self.designs if item.existing_template_ref]
        if len(refs) != len(set(refs)):
            raise ValueError("existing deep template references must be unique")
        return self


class ScenarioSimilarityPair(StrictModel):
    design_a: str = Field(pattern=IDENTIFIER_PATTERN)
    design_b: str = Field(pattern=IDENTIFIER_PATTERN)
    similarity: float = Field(ge=0, le=1)
    shared_terms: list[str]


class ScenarioLibraryAudit(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    audit_passed: bool
    design_count: Literal[240] = 240
    family_count: Literal[30] = 30
    exact_signature_collisions: list[list[str]]
    duplicate_titles: list[list[str]]
    duplicate_questions: list[list[str]]
    high_similarity_threshold: float = Field(gt=0, le=1)
    maximum_pairwise_similarity: float = Field(ge=0, le=1)
    high_similarity_pairs: list[ScenarioSimilarityPair]
    suite_counts: dict[ApplicationSuite, int]
    family_counts: dict[ApplicationSuite, int]
    decision_type_counts: dict[DecisionType, int]
    horizon_counts: dict[DecisionHorizon, int]
    spatial_unit_counts: dict[SpatialUnit, int]
    analysis_mode_counts: dict[AnalysisMode, int]
    evidence_type_counts: dict[EvidenceType, int]
    source_role_counts: dict[LibrarySourceRole, int]
    gate_type_counts: dict[EvidenceGateType, int]
    constraint_kind_counts: dict[DesignConstraintKind, int]
    implementation_status_counts: dict[ImplementationStatus, int]
    current_readiness_counts: dict[CurrentReadiness, int]
    existing_template_refs: int = Field(ge=0)
    city_bound_executions_counted: Literal[0] = 0
    methods_claimed: Literal[0] = 0
    completeness_checks: dict[str, int]
    invariants: list[str] = Field(min_length=8)
    limitations: list[str] = Field(min_length=3)

    @model_validator(mode="after")
    def audit_integrity(self) -> ScenarioLibraryAudit:
        expected_pass = not (
            self.exact_signature_collisions
            or self.duplicate_titles
            or self.duplicate_questions
            or self.high_similarity_pairs
        ) and all(value == 240 for value in self.completeness_checks.values())
        if self.audit_passed != expected_pass:
            raise ValueError("scenario library audit status does not match its diagnostics")
        if sum(self.suite_counts.values()) != 240 or sum(self.family_counts.values()) != 30:
            raise ValueError("scenario library audit suite counts do not reconcile")
        if set(self.decision_type_counts) != set(DecisionType) or any(
            value != 30 for value in self.decision_type_counts.values()
        ):
            raise ValueError("scenario library audit lacks the 30-by-8 design matrix")
        return self


class ScenarioLibraryArtifactEntry(StrictModel):
    path: str
    media_type: str = Field(min_length=3)
    byte_count: int = Field(ge=1)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    record_count: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return _safe_relative_posix_path(value)


class ScenarioLibraryManifest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    published_at: datetime
    library_content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    artifact_count: int = Field(ge=1)
    artifacts: list[ScenarioLibraryArtifactEntry] = Field(min_length=1)
    claim_boundary: list[str] = Field(min_length=4)

    @field_validator("published_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "scenario library manifest published_at")

    @model_validator(mode="after")
    def manifest_integrity(self) -> ScenarioLibraryManifest:
        if self.artifact_count != len(self.artifacts):
            raise ValueError("scenario library artifact count must match entries")
        paths = [item.path for item in self.artifacts]
        if paths != sorted(set(paths)):
            raise ValueError("scenario library artifact paths must be sorted and unique")
        return self


__all__ = [
    "CurrentReadiness",
    "DecisionHorizon",
    "DecisionType",
    "DesignConstraintKind",
    "EvidenceGateType",
    "ImplementationStatus",
    "LibrarySourceRole",
    "ScenarioDesign",
    "ScenarioDesignConstraint",
    "ScenarioDesignIndexEntry",
    "ScenarioDesignObjective",
    "ScenarioEvidenceGate",
    "ScenarioFamily",
    "ScenarioFamilyIndexEntry",
    "ScenarioIndependenceKey",
    "ScenarioLibraryArtifactEntry",
    "ScenarioLibraryAudit",
    "ScenarioLibraryManifest",
    "ScenarioLibraryRegistry",
    "ScenarioSimilarityPair",
    "SpatialUnit",
]
