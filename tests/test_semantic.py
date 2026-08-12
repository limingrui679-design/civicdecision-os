from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.core import (
    Coordinate,
    EventKind,
    Facility,
    FacilityKind,
    Geography,
    GeographyKind,
    MeasureDefinition,
    MeasureValueKind,
    Observation,
    SemanticBundle,
    TimeInterval,
    UrbanEvent,
)
from civicdecision.semantic.graph import (
    UrbanEdge,
    UrbanEdgeKind,
    UrbanGraphBundle,
    UrbanNode,
    UrbanNodeKind,
)


def interval() -> TimeInterval:
    return TimeInterval(
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 1, tzinfo=UTC),
        resolution="day",
    )


def geography() -> Geography:
    return Geography(
        id="city.a",
        name="A",
        kind=GeographyKind.CITY,
        country_code="AA",
        centroid=Coordinate(latitude=1, longitude=2),
        source_refs=["source-a"],
        limitations=["Fixture."],
    )


def measure() -> MeasureDefinition:
    return MeasureDefinition(
        id="measure.a",
        name="Measure A",
        value_kind=MeasureValueKind.COUNT,
        unit="people",
        description="Fixture measure.",
        valid_min=0,
        limitations=["Fixture."],
    )


def test_semantic_bundle_validates_references(source_manifest: SourceManifest) -> None:
    bundle = SemanticBundle(
        bundle_id="bundle.a",
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        source_manifests=[source_manifest],
        geographies=[geography()],
        measures=[measure()],
        observations=[
            Observation(
                id="observation.a",
                geography_id="city.a",
                measure_id="measure.a",
                interval=interval(),
                value=1,
                evidence_type=EvidenceType.OBSERVED,
                source_ref="source-a",
                limitations=["Fixture."],
            )
        ],
        facilities=[
            Facility(
                id="facility.a",
                name="Facility A",
                kind=FacilityKind.HEALTH,
                geography_id="city.a",
                status="open",
                source_refs=["source-a"],
                limitations=["Fixture."],
            )
        ],
        events=[
            UrbanEvent(
                id="event.a",
                name="Event A",
                kind=EventKind.WEATHER,
                interval=interval(),
                geography_ids=["city.a"],
                evidence_type=EvidenceType.OBSERVED,
                source_refs=["source-a"],
                limitations=["Fixture."],
            )
        ],
        limitations=["Fixture."],
    )
    assert bundle.content_hash().startswith("sha256:")


def test_semantic_model_gates() -> None:
    with pytest.raises(ValidationError, match="valid_min"):
        MeasureDefinition(
            id="measure.bad",
            name="Bad",
            value_kind=MeasureValueKind.RATE,
            unit="percent",
            description="Bad range.",
            valid_min=10,
            valid_max=1,
            limitations=["Fixture."],
        )
    with pytest.raises(ValidationError, match="start cannot be later"):
        TimeInterval(
            start=datetime(2025, 1, 2, tzinfo=UTC),
            end=datetime(2025, 1, 1, tzinfo=UTC),
            resolution="day",
        )
    with pytest.raises(ValidationError, match="observed or estimated"):
        Observation(
            id="observation.bad",
            geography_id="city.a",
            measure_id="measure.a",
            interval=interval(),
            value=1,
            evidence_type=EvidenceType.CAUSAL,
            source_ref="source-a",
            limitations=["Fixture."],
        )
    with pytest.raises(ValidationError, match="require a method"):
        Observation(
            id="observation.bad",
            geography_id="city.a",
            measure_id="measure.a",
            interval=interval(),
            value=1,
            evidence_type=EvidenceType.ESTIMATED,
            source_ref="source-a",
            limitations=["Fixture."],
        )
    with pytest.raises(ValidationError, match="observed, estimated, or proposed"):
        UrbanEvent(
            id="event.bad",
            name="Bad",
            kind=EventKind.OTHER,
            interval=interval(),
            geography_ids=["city.a"],
            evidence_type=EvidenceType.OPTIMIZED,
            source_refs=["source-a"],
            limitations=["Fixture."],
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("geographies", [geography(), geography()], "geography ids"),
        (
            "geographies",
            [Geography(**{**geography().model_dump(), "parent_ids": ["missing"]})],
            "parent reference",
        ),
    ],
)
def test_semantic_bundle_rejects_duplicate_or_missing_geographies(
    source_manifest: SourceManifest,
    field: str,
    value: object,
    message: str,
) -> None:
    payload = {
        "bundle_id": "bundle.bad",
        "created_at": datetime(2026, 8, 12, tzinfo=UTC),
        "source_manifests": [source_manifest],
        "geographies": [geography()],
        "limitations": ["Fixture."],
    }
    payload[field] = value
    with pytest.raises(ValidationError, match=message):
        SemanticBundle.model_validate(payload)


def test_graph_validates_evidence_and_endpoints() -> None:
    node = UrbanNode(
        id="city.a",
        kind=UrbanNodeKind.CITY,
        label="A",
        source_refs=["source-a"],
        limitations=["Fixture."],
    )
    edge = UrbanEdge(
        id="edge.a",
        kind=UrbanEdgeKind.LOCATED_IN,
        source_node_id="city.a",
        target_node_id="country.aa",
        evidence_type=EvidenceType.OBSERVED,
        source_refs=["source-a"],
        limitations=["Fixture."],
    )
    with pytest.raises(ValidationError, match="endpoint"):
        UrbanGraphBundle(
            graph_id="graph.bad",
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
            nodes=[node],
            edges=[edge],
            source_hashes=["sha256:" + "0" * 64],
            limitations=["Fixture."],
        )
    with pytest.raises(ValidationError, match="cannot claim causal"):
        UrbanEdge(**{**edge.model_dump(), "evidence_type": EvidenceType.CAUSAL})
    graph = UrbanGraphBundle(
        graph_id="graph.a",
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        nodes=[
            node,
            UrbanNode(
                id="country.aa",
                kind=UrbanNodeKind.COUNTRY_OR_TERRITORY,
                label="AA",
                source_refs=["source-a"],
                limitations=["Fixture."],
            ),
        ],
        edges=[edge],
        source_hashes=["sha256:" + "0" * 64],
        limitations=["Fixture."],
    )
    assert graph.content_hash().startswith("sha256:")


@pytest.mark.parametrize("kind", ["nodes", "edges"])
def test_graph_rejects_duplicate_ids(kind: str) -> None:
    node = UrbanNode(
        id="city.a",
        kind=UrbanNodeKind.CITY,
        label="A",
        source_refs=["source-a"],
        limitations=["Fixture."],
    )
    edge = UrbanEdge(
        id="edge.a",
        kind=UrbanEdgeKind.CONNECTED_TO,
        source_node_id="city.a",
        target_node_id="city.a",
        evidence_type=EvidenceType.SIMULATED,
        source_refs=["source-a"],
        limitations=["Fixture."],
    )
    payload = {
        "graph_id": "graph.bad",
        "created_at": datetime(2026, 8, 12, tzinfo=UTC),
        "nodes": [node, node] if kind == "nodes" else [node],
        "edges": [edge, edge] if kind == "edges" else [edge],
        "source_hashes": ["sha256:" + "0" * 64],
        "limitations": ["Fixture."],
    }
    with pytest.raises(ValidationError, match=f"{kind[:-1]} ids"):
        UrbanGraphBundle.model_validate(payload)
