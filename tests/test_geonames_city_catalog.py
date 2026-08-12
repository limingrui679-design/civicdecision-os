from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest
from pydantic import ValidationError

from civicdecision.connectors.base import write_manifest
from civicdecision.connectors.geonames import (
    GEONAMES_MEMBER,
    GeoNamesCitiesConnector,
    GeoNamesCitiesQuery,
    validate_geonames_zip,
)
from civicdecision.errors import AnalysisError, ConnectorError
from civicdecision.protocols.base import sha256_bytes
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.city_catalog import (
    GeoNamesCityRecord,
    GlobalCityCatalog,
    build_city_seed_graph,
    build_city_semantic_bundle,
    build_global_city_catalog,
    write_catalog_artifacts,
)
from civicdecision.semantic.core import SemanticBundle
from civicdecision.semantic.graph import UrbanGraphBundle


def city_row(
    identifier: int,
    name: str,
    country: str,
    population: int,
    *,
    timezone: str = "Etc/UTC",
) -> str:
    return "\t".join(
        [
            str(identifier),
            name,
            name,
            "",
            "1.0",
            "2.0",
            "P",
            "PPLA",
            country,
            "",
            "01",
            "",
            "",
            "",
            str(population),
            "",
            "0",
            timezone,
            "2026-01-01",
        ]
    )


def zip_content(rows: list[str], member: str = GEONAMES_MEMBER) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(member, ("\n".join(rows) + "\n").encode("utf-8"))
    return buffer.getvalue()


def catalog_fixture(tmp_path: Path, rows: list[str]) -> Path:
    content = zip_content(rows)
    artifact = tmp_path / "cities.zip"
    artifact.write_bytes(content)
    manifest = SourceManifest(
        source_id="geonames-cities15000",
        artifact_id="geonames-fixture",
        name="GeoNames fixture",
        publisher="GeoNames",
        landing_url="https://download.geonames.org/export/dump/",
        data_url="https://download.geonames.org/export/dump/cities15000.zip",
        license="CC BY 4.0",
        retrieved_at=datetime(2026, 8, 12, tzinfo=UTC),
        query=GeoNamesCitiesQuery().model_dump(mode="json"),
        artifact_path=artifact.name,
        content_hash=sha256_bytes(content),
        record_count=len(rows),
        schema_fingerprint="sha256:" + "1" * 64,
        geographic_scope="fixture",
        temporal_scope="fixture",
        limitations=["Fixture only."],
    )
    manifest_path = tmp_path / "cities.manifest.json"
    write_manifest(manifest_path, manifest)
    return manifest_path


@pytest.mark.asyncio
async def test_geonames_connector_validates_zip_and_manifest(tmp_path: Path) -> None:
    content = zip_content([city_row(1, "Alpha", "AA", 100)])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=content,
            request=request,
            headers={"Last-Modified": "Wed, 12 Aug 2026 03:59:00 GMT"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GeoNamesCitiesConnector().fetch(GeoNamesCitiesQuery(), tmp_path, client)
    assert result.manifest.record_count == 1
    assert result.manifest.upstream_updated_at == datetime(2026, 8, 12, 3, 59, tzinfo=UTC)
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not-a-zip", "invalid ZIP"),
        (zip_content([city_row(1, "A", "AA", 1)], "../escape.txt"), "only cities15000"),
        (zip_content([], GEONAMES_MEMBER), "empty"),
        (zip_content(["too\tfew"], GEONAMES_MEMBER), "19 columns"),
    ],
)
def test_geonames_zip_rejects_unsafe_archives(content: bytes, message: str) -> None:
    with pytest.raises(ConnectorError, match=message):
        validate_geonames_zip(content, GeoNamesCitiesQuery())


def test_geonames_zip_size_and_encoding_gates() -> None:
    with pytest.raises(ConnectorError, match="compressed-size"):
        validate_geonames_zip(b"x" * 1_000_001, GeoNamesCitiesQuery(max_compressed_bytes=1_000_000))
    oversized = zip_content(["x" * 5_000_001])
    with pytest.raises(ConnectorError, match="uncompressed-size"):
        validate_geonames_zip(
            oversized,
            GeoNamesCitiesQuery(max_uncompressed_bytes=5_000_000),
        )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(GEONAMES_MEMBER, b"\xff\xfe")
    with pytest.raises(ConnectorError, match="UTF-8"):
        validate_geonames_zip(buffer.getvalue(), GeoNamesCitiesQuery())


@pytest.mark.asyncio
async def test_geonames_connector_wraps_http_and_header_failures(tmp_path: Path) -> None:
    def http_failure(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(http_failure)) as client:
        with pytest.raises(ConnectorError, match="request failed safely"):
            await GeoNamesCitiesConnector().fetch(GeoNamesCitiesQuery(), tmp_path, client)

    content = zip_content([city_row(1, "Alpha", "AA", 100)])

    def bad_header(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=content, request=request, headers={"Last-Modified": "bad"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(bad_header)) as client:
        with pytest.raises(ConnectorError, match="Last-Modified"):
            await GeoNamesCitiesConnector().fetch(GeoNamesCitiesQuery(), tmp_path, client)


def fixture_rows() -> list[str]:
    return [
        city_row(1, "A leader", "AA", 1000),
        city_row(2, "A second", "AA", 900),
        city_row(3, "B leader", "BB", 800),
        city_row(4, "C leader", "CC", 700),
        city_row(5, "D leader", "DD", 600),
        city_row(6, "B second", "BB", 500),
    ]


def test_global_city_selection_prioritizes_country_breadth_then_population(
    tmp_path: Path,
) -> None:
    manifest = catalog_fixture(tmp_path, fixture_rows())
    catalog = build_global_city_catalog(manifest, target_count=5)
    assert len(catalog.cities) == 5
    assert catalog.country_or_territory_count == 4
    assert [item.selection_rank for item in catalog.cities] == [1, 2, 3, 4, 5]
    assert [item.selection_basis for item in catalog.cities].count("country-leader") == 4
    assert catalog.cities[-1].selection_basis == "global-fill"
    assert catalog.cities[-1].geoname_id == 2
    assert catalog.content_hash() == catalog.content_hash()


def test_catalog_builds_semantic_bundle_graph_and_portable_artifacts(
    tmp_path: Path,
) -> None:
    manifest = catalog_fixture(tmp_path, fixture_rows())
    catalog = build_global_city_catalog(manifest, target_count=5)
    semantic = build_city_semantic_bundle(catalog)
    graph = build_city_seed_graph(catalog)
    assert len(semantic.geographies) == 9
    assert len(graph.nodes) == 9
    assert len(graph.edges) == 5
    artifacts = write_catalog_artifacts(catalog, tmp_path / "output")
    assert GlobalCityCatalog.model_validate_json(artifacts.catalog_path.read_bytes())
    assert SemanticBundle.model_validate_json(artifacts.semantic_bundle_path.read_bytes())
    assert UrbanGraphBundle.model_validate_json(artifacts.graph_path.read_bytes())
    coverage_lines = artifacts.coverage_matrix_path.read_text().splitlines()
    assert len(coverage_lines) == 6
    assert coverage_lines[0].startswith("selection_rank,city_id,name")
    checksum = artifacts.checksum_path.read_text()
    assert str(tmp_path) not in checksum
    assert checksum.count("\n") == 4


def test_catalog_input_and_target_failures(tmp_path: Path) -> None:
    manifest = catalog_fixture(tmp_path, fixture_rows())
    with pytest.raises(AnalysisError, match="positive"):
        build_global_city_catalog(manifest, target_count=0)
    with pytest.raises(AnalysisError, match="exceeds"):
        build_global_city_catalog(manifest, target_count=7)

    payload = json.loads(manifest.read_text())
    payload["record_count"] = 99
    manifest.write_text(json.dumps(payload))
    with pytest.raises(AnalysisError, match="record count mismatch"):
        build_global_city_catalog(manifest, target_count=1)


def test_catalog_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    rows = [city_row(1, "A", "AA", 10), city_row(1, "B", "BB", 9)]
    manifest = catalog_fixture(tmp_path, rows)
    with pytest.raises(AnalysisError, match="duplicate"):
        build_global_city_catalog(manifest, target_count=1)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda row: row.replace("\tP\tPPLA\t", "\tA\tPPLA\t"), "feature class"),
        (lambda row: row.replace("Etc/UTC", "Mars/Olympus"), "timezone"),
        (lambda row: row.rsplit("\t", 1)[0] + "\tnot-a-date", "isoformat"),
    ],
)
def test_geonames_row_semantics_are_strict(mutator: object, message: str) -> None:
    mutate = mutator
    with pytest.raises((ValueError, ValidationError), match=message):
        GeoNamesCityRecord.from_tsv(mutate(city_row(1, "A", "AA", 1)))  # type: ignore[operator]
