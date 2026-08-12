"""Evidence-typed urban knowledge-graph interchange contract."""

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


class UrbanNodeKind(StrEnum):
    COUNTRY_OR_TERRITORY = "country-or-territory"
    CITY = "city"
    ADMINISTRATIVE_AREA = "administrative-area"
    FACILITY = "facility"
    NETWORK = "network"
    EVENT = "event"
    MEASURE = "measure"
    POPULATION_GROUP = "population-group"
    POLICY = "policy"
    ASSET = "asset"


class UrbanEdgeKind(StrEnum):
    LOCATED_IN = "located-in"
    CONNECTED_TO = "connected-to"
    SERVES = "serves"
    EXPOSED_TO = "exposed-to"
    AFFECTS = "affects"
    MEASURED_BY = "measured-by"
    DERIVED_FROM = "derived-from"
    CANDIDATE_FOR = "candidate-for"


class UrbanNode(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: UrbanNodeKind
    label: str = Field(min_length=1)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class UrbanEdge(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: UrbanEdgeKind
    source_node_id: str = Field(pattern=IDENTIFIER_PATTERN)
    target_node_id: str = Field(pattern=IDENTIFIER_PATTERN)
    directed: bool = True
    evidence_type: EvidenceType
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def supported_evidence(cls, value: EvidenceType) -> EvidenceType:
        if value not in {
            EvidenceType.OBSERVED,
            EvidenceType.ESTIMATED,
            EvidenceType.SIMULATED,
            EvidenceType.PROPOSED,
        }:
            raise ValueError("graph edges cannot claim causal or optimized evidence")
        return value


class UrbanGraphBundle(StrictModel):
    schema_version: str = "1.0.0"
    graph_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    nodes: list[UrbanNode] = Field(min_length=1)
    edges: list[UrbanEdge] = Field(default_factory=list)
    source_hashes: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "urban graph created_at")

    @model_validator(mode="after")
    def graph_integrity(self) -> UrbanGraphBundle:
        node_ids = [item.id for item in self.nodes]
        edge_ids = [item.id for item in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("urban graph node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("urban graph edge ids must be unique")
        node_set = set(node_ids)
        if any(
            edge.source_node_id not in node_set or edge.target_node_id not in node_set
            for edge in self.edges
        ):
            raise ValueError("urban graph edge endpoint does not exist")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))
