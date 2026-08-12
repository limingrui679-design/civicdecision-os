"""Canonical geography, time, measure, observation, facility, and event semantics."""

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
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest


class Coordinate(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeographyKind(StrEnum):
    COUNTRY_OR_TERRITORY = "country-or-territory"
    REGION = "region"
    CITY = "city"
    ADMINISTRATIVE_AREA = "administrative-area"
    TRACT = "tract"
    POINT = "point"


class Geography(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    kind: GeographyKind
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    centroid: Coordinate | None = None
    parent_ids: list[str] = Field(default_factory=list)
    codes: dict[str, str] = Field(default_factory=dict)
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("parent_ids", "source_refs")
    @classmethod
    def unique_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("geography references must be unique")
        return value


class MeasureValueKind(StrEnum):
    COUNT = "count"
    RATE = "rate"
    INDEX = "index"
    CURRENCY = "currency"
    TEMPERATURE = "temperature"
    DISTANCE = "distance"
    DURATION = "duration"
    BOOLEAN = "boolean"
    CATEGORY = "category"
    OTHER = "other"


class MeasureDefinition(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    value_kind: MeasureValueKind
    unit: str = Field(min_length=1)
    description: str = Field(min_length=1)
    valid_min: float | None = None
    valid_max: float | None = None
    numerator_measure_id: str | None = None
    denominator_measure_id: str | None = None
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_range(self) -> MeasureDefinition:
        if (
            self.valid_min is not None
            and self.valid_max is not None
            and self.valid_min > self.valid_max
        ):
            raise ValueError("measure valid_min cannot exceed valid_max")
        return self


class TimeInterval(StrictModel):
    start: datetime
    end: datetime
    resolution: str = Field(min_length=1)

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "semantic interval datetime")

    @model_validator(mode="after")
    def ordered(self) -> TimeInterval:
        if self.start > self.end:
            raise ValueError("semantic interval start cannot be later than end")
        return self


class Observation(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    geography_id: str = Field(pattern=IDENTIFIER_PATTERN)
    measure_id: str = Field(pattern=IDENTIFIER_PATTERN)
    interval: TimeInterval
    value: float | int | str | bool | None
    evidence_type: EvidenceType
    source_ref: str = Field(min_length=1)
    method: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_gate(self) -> Observation:
        if self.evidence_type not in {EvidenceType.OBSERVED, EvidenceType.ESTIMATED}:
            raise ValueError("semantic source observations must be observed or estimated")
        if self.evidence_type is EvidenceType.ESTIMATED and not self.method:
            raise ValueError("estimated semantic observations require a method")
        return self


class FacilityKind(StrEnum):
    HEALTH = "health"
    SHELTER = "shelter"
    COOLING = "cooling"
    EDUCATION = "education"
    TRANSIT = "transit"
    EMERGENCY = "emergency"
    UTILITY = "utility"
    OTHER = "other"


class Facility(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    kind: FacilityKind
    geography_id: str = Field(pattern=IDENTIFIER_PATTERN)
    location: Coordinate | None = None
    status: str = Field(min_length=1)
    capacity: float | None = Field(default=None, ge=0)
    capacity_unit: str | None = None
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class EventKind(StrEnum):
    WEATHER = "weather"
    DISASTER = "disaster"
    SERVICE = "service"
    INFRASTRUCTURE = "infrastructure"
    POLICY = "policy"
    OTHER = "other"


class UrbanEvent(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    kind: EventKind
    interval: TimeInterval
    geography_ids: list[str] = Field(min_length=1)
    evidence_type: EvidenceType
    source_refs: list[str] = Field(min_length=1)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def valid_evidence(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.OBSERVED, EvidenceType.ESTIMATED, EvidenceType.PROPOSED}:
            raise ValueError("semantic events must be observed, estimated, or proposed")
        return value


class SemanticBundle(StrictModel):
    schema_version: str = "1.0.0"
    bundle_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    source_manifests: list[SourceManifest] = Field(min_length=1)
    geographies: list[Geography] = Field(min_length=1)
    measures: list[MeasureDefinition] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    facilities: list[Facility] = Field(default_factory=list)
    events: list[UrbanEvent] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "semantic bundle created_at")

    @model_validator(mode="after")
    def referential_integrity(self) -> SemanticBundle:
        groups = {
            "geography": [item.id for item in self.geographies],
            "measure": [item.id for item in self.measures],
            "observation": [item.id for item in self.observations],
            "facility": [item.id for item in self.facilities],
            "event": [item.id for item in self.events],
        }
        for name, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{name} ids must be unique")
        geography_ids = set(groups["geography"])
        measure_ids = set(groups["measure"])
        if any(
            parent not in geography_ids
            for geography in self.geographies
            for parent in geography.parent_ids
        ):
            raise ValueError("geography parent reference does not exist")
        if any(
            item.geography_id not in geography_ids or item.measure_id not in measure_ids
            for item in self.observations
        ):
            raise ValueError("observation geography or measure reference does not exist")
        if any(item.geography_id not in geography_ids for item in self.facilities):
            raise ValueError("facility geography reference does not exist")
        if any(
            geography_id not in geography_ids
            for event in self.events
            for geography_id in event.geography_ids
        ):
            raise ValueError("event geography reference does not exist")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))
