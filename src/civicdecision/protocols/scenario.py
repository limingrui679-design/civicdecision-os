"""Policy Scenario DSL."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import IDENTIFIER_PATTERN, JsonValue, StrictModel, ensure_aware
from civicdecision.protocols.evidence import EvidenceType


class AnalysisMode(StrEnum):
    DESCRIPTIVE = "descriptive"
    FORECAST = "forecast"
    CAUSAL = "causal"
    SIMULATION = "simulation"
    OPTIMIZATION = "optimization"


class Intervention(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: str = Field(pattern=IDENTIFIER_PATTERN)
    target: str = Field(min_length=1)
    parameters: dict[str, JsonValue]
    evidence_type: EvidenceType = EvidenceType.PROPOSED

    @field_validator("evidence_type")
    @classmethod
    def intervention_is_not_observed_outcome(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OBSERVED, EvidenceType.PROPOSED, EvidenceType.SIMULATED}:
            raise ValueError("interventions may only be observed, proposed, or simulated")
        return value


class Objective(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    metric: str = Field(min_length=1)
    sense: str = Field(pattern=r"^(minimize|maximize)$")
    weight: float = Field(gt=0)
    unit: str = Field(min_length=1)


class Constraint(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    expression: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(budget|capacity|equity|risk|time|regulatory|custom)$")
    hard: bool = True
    source_ref: str | None = None


class PolicyScenario(StrictModel):
    schema_version: str = "1.0.0"
    scenario_id: str = Field(pattern=IDENTIFIER_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    as_of: datetime
    data_cutoff: datetime
    baseline: str = Field(min_length=1)
    interventions: list[Intervention] = Field(min_length=1)
    objectives: list[Objective] = Field(min_length=1)
    constraints: list[Constraint] = Field(min_length=1)
    analysis_modes: list[AnalysisMode] = Field(min_length=1)
    evidence_requirements: list[EvidenceType] = Field(min_length=1)
    random_seed: int = Field(ge=0, le=2**32 - 1)
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("as_of", "data_cutoff")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "scenario datetime")

    @model_validator(mode="after")
    def validate_scenario(self) -> PolicyScenario:
        if self.data_cutoff > self.as_of:
            raise ValueError("data_cutoff cannot be later than as_of")
        unique_groups = [
            ("intervention ids", [item.id for item in self.interventions]),
            ("objective ids", [item.id for item in self.objectives]),
            ("constraint ids", [item.id for item in self.constraints]),
            ("analysis modes", [mode.value for mode in self.analysis_modes]),
            ("evidence requirements", [item.value for item in self.evidence_requirements]),
        ]
        for name, values in unique_groups:
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
        if (
            AnalysisMode.CAUSAL in self.analysis_modes
            and EvidenceType.CAUSAL not in self.evidence_requirements
        ):
            raise ValueError("causal mode requires causal evidence requirements")
        return self
