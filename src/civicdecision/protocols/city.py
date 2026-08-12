"""City Adapter protocol."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel, ensure_aware


class CityTier(StrEnum):
    GLOBAL = "G"
    STANDARDIZED = "S"
    DEEP = "D"


class BoundingBox(StrictModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def ordered(self) -> BoundingBox:
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("bounding box must have west < east and south < north")
        return self


class CoverageWindow(StrictModel):
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "coverage datetime")

    @model_validator(mode="after")
    def ordered(self) -> CoverageWindow:
        if self.start >= self.end:
            raise ValueError("coverage start must be earlier than end")
        return self


class CityAdapterManifest(StrictModel):
    schema_version: str = "1.0.0"
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1)
    country_code: str = Field(min_length=2, max_length=2)
    tier: CityTier
    timezone: str
    bbox: BoundingBox
    coverage: CoverageWindow | None = None
    source_ids: list[str] = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    data_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @field_validator("country_code")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("country_code must contain letters only")
        return value.upper()

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("source_ids", "capabilities")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value
