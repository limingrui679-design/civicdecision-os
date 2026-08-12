"""DecisionPack protocol, including negative-evidence releases."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    JsonValue,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceItem, EvidenceType
from civicdecision.protocols.source import SourceManifest


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INFEASIBLE = "infeasible"
    TIMED_OUT = "timed_out"


class ReversalOutcome(StrEnum):
    REVERSED = "reversed"
    STABLE = "stable"
    INCONCLUSIVE = "inconclusive"


class DecisionOption(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: str = Field(min_length=1)
    evidence_type: EvidenceType
    feasible: bool
    metrics: dict[str, float | int | str | None]
    binding_constraints: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def option_type(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OPTIMIZED, EvidenceType.PROPOSED, EvidenceType.SIMULATED}:
            raise ValueError("decision options must be optimized, proposed, or simulated")
        return value


class Recommendation(StrictModel):
    selected_option_id: str | None = None
    evidence_type: EvidenceType
    rationale: str = Field(min_length=1)
    reversal_conditions: list[str] = Field(default_factory=list)
    required_next_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def recommendation_type(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OPTIMIZED, EvidenceType.PROPOSED}:
            raise ValueError("a recommendation must be optimized or proposed")
        return value


class ReversalTest(StrictModel):
    """A controlled sensitivity test that can overturn a selected option."""

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    parameter: str = Field(min_length=1)
    baseline_value: float | int | str | bool
    tested_value: float | int | str | bool
    unit: str = Field(min_length=1)
    baseline_option_id: str | None = None
    selected_option_id_after_test: str | None = None
    outcome: ReversalOutcome
    evidence_type: EvidenceType
    method: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def sensitivity_evidence_type(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.ESTIMATED, EvidenceType.SIMULATED}:
            raise ValueError("reversal tests must be estimated or simulated")
        return value


class ValueOfInformation(StrictModel):
    """A ranked evidence gap whose resolution could change the decision."""

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    uncertainty: str = Field(min_length=1)
    decision_link: str = Field(min_length=1)
    collection_action: str = Field(min_length=1)
    priority_score: float = Field(ge=0, le=1)
    evidence_type: EvidenceType = EvidenceType.PROPOSED
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def voi_is_proposed(cls, value: EvidenceType) -> EvidenceType:
        if value is not EvidenceType.PROPOSED:
            raise ValueError("value-of-information items must be proposed")
        return value


class Reproducibility(StrictModel):
    software_version: str = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    random_seed: int = Field(ge=0, le=2**32 - 1)
    environment: dict[str, str] = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(min_length=1)
    source_hashes: list[str] = Field(min_length=1)


class DecisionPack(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    status: RunStatus
    source_manifests: list[SourceManifest] = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(min_length=1)
    options: list[DecisionOption] = Field(default_factory=list)
    recommendation: Recommendation
    reversal_tests: list[ReversalTest] = Field(default_factory=list)
    value_of_information: list[ValueOfInformation] = Field(default_factory=list)
    failure_reason: str | None = None
    reproducibility: Reproducibility

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_outcome(self) -> DecisionPack:
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("decision option ids must be unique")
        selected = self.recommendation.selected_option_id
        if self.status is RunStatus.COMPLETED:
            if not selected:
                raise ValueError("completed runs require a selected option")
            if selected not in option_ids:
                raise ValueError("selected option does not exist")
            selected_option = next(option for option in self.options if option.id == selected)
            if not selected_option.feasible:
                raise ValueError("selected option must be feasible")
            if not self.reversal_tests:
                raise ValueError("completed runs require at least one reversal test")
            if not self.value_of_information:
                raise ValueError("completed runs require value-of-information guidance")
        else:
            if selected is not None:
                raise ValueError("negative runs cannot select an option")
            if not self.failure_reason:
                raise ValueError("negative runs require a failure reason")
            if not self.recommendation.required_next_evidence:
                raise ValueError("negative runs require next-evidence guidance")
        return self

    def content_hash(self) -> str:
        """Hash the full canonical pack."""

        return sha256_bytes(canonical_json(self))
