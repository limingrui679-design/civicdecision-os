"""Typed contracts for data-only CivicDecision adapter packages."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel
from civicdecision.protocols.city import CityAdapterManifest


class PluginCapability(StrEnum):
    """Capabilities that may be declared without executing third-party code."""

    CITY_ADAPTER = "city-adapter"
    SOURCE_BINDING = "source-binding"
    SEMANTIC_MAPPING = "semantic-mapping"


class PluginManifest(StrictModel):
    """Signed-shape descriptor for one portable, data-only plugin directory."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    plugin_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(
        pattern=r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$"
    )
    api_version: Literal["1"] = "1"
    description: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=120)
    license: str = Field(min_length=1, max_length=80)
    capabilities: list[PluginCapability] = Field(min_length=1)
    adapter_paths: list[str] = Field(min_length=1, max_length=250)
    artifact_hashes: dict[str, str] = Field(min_length=1, max_length=250)
    evidence_boundary: list[str] = Field(min_length=1, max_length=20)
    enabled_by_default: Literal[False] = False

    @field_validator("capabilities")
    @classmethod
    def sorted_unique_capabilities(cls, value: list[PluginCapability]) -> list[PluginCapability]:
        if value != sorted(set(value), key=str):
            raise ValueError("plugin capabilities must be sorted and unique")
        return value

    @field_validator("adapter_paths")
    @classmethod
    def safe_sorted_adapter_paths(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("plugin adapter paths must be sorted and unique")
        for path in value:
            if not path.startswith("adapters/") or not path.endswith(".json"):
                raise ValueError("plugin adapter paths must use adapters/*.json")
            if (
                "\\" in path
                or "//" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError("plugin adapter paths must be normalized relative paths")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def valid_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if list(value) != sorted(value):
            raise ValueError("plugin artifact hash keys must be sorted")
        if any(not digest.startswith("sha256:") or len(digest) != 71 for digest in value.values()):
            raise ValueError("plugin artifacts require namespaced SHA-256 hashes")
        return value

    @model_validator(mode="after")
    def package_shape(self) -> PluginManifest:
        if PluginCapability.CITY_ADAPTER not in self.capabilities:
            raise ValueError("version 1 plugin packages must declare city-adapter capability")
        if set(self.adapter_paths) != set(self.artifact_hashes):
            raise ValueError("plugin adapter paths and artifact hash keys must match")
        return self


class PluginPackage(StrictModel):
    """Validated in-memory projection of a plugin directory."""

    manifest: PluginManifest
    adapters: list[CityAdapterManifest] = Field(min_length=1, max_length=250)
    package_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_cities(self) -> PluginPackage:
        city_ids = [adapter.city_id for adapter in self.adapters]
        if len(city_ids) != len(set(city_ids)):
            raise ValueError("plugin city adapter identifiers must be unique")
        if len(self.adapters) != len(self.manifest.adapter_paths):
            raise ValueError("plugin adapter count must match manifest paths")
        return self


class PluginPackageSummary(StrictModel):
    """Safe registry view that does not expose a filesystem path."""

    plugin_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    capabilities: list[PluginCapability] = Field(min_length=1)
    city_adapters: int = Field(ge=1)
    city_ids: list[str] = Field(min_length=1)
    package_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_boundary: list[str] = Field(min_length=1)

    @field_validator("city_ids")
    @classmethod
    def sorted_unique_city_ids(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("plugin summary city identifiers must be sorted and unique")
        return value


__all__ = [
    "PluginCapability",
    "PluginManifest",
    "PluginPackage",
    "PluginPackageSummary",
]
