from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from civicdecision.connectors.census_places import (
    ACSMarginStatus,
    CensusACSPopulationTableConnector,
    CensusPlaceQuery,
    CensusPopulationArtifact,
    CensusPopulationQuery,
    CensusTIGERPlaceConnector,
)
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import sha256_bytes


def _population_table(*rows: str) -> bytes:
    return ("GEO_ID|B01003_E001|B01003_M001\n" + "\n".join(rows) + "\n").encode()


def _tiger_payload(query: CensusPlaceQuery) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"GEOID": query.geoid, "NAME": "Boston city"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-71.2, 42.2], [-70.9, 42.2], [-70.9, 42.4], [-71.2, 42.2]]],
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_census_population_connector_filters_and_preserves_margins(
    tmp_path: Path,
) -> None:
    query = CensusPopulationQuery(geoids=("2507000", "3651000"))
    body = _population_table(
        "1600000US3651000|8336817|-555555555",
        "1600000US2507000|653833|1012",
        "1600000US9999999|42|7",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"etag": '"population-v1"', "content-type": "text/plain"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CensusACSPopulationTableConnector().fetch(query, tmp_path, client)

    artifact = CensusPopulationArtifact.model_validate_json(result.artifact_path.read_bytes())
    assert result.manifest.record_count == 2
    assert [row.geoid for row in artifact.rows] == ["2507000", "3651000"]
    assert artifact.rows[0].margin_status is ACSMarginStatus.AVAILABLE
    assert artifact.rows[0].margin_of_error_90 == 1012
    assert artifact.rows[1].margin_status is ACSMarginStatus.CONTROLLED
    assert artifact.rows[1].margin_of_error_90 == 0
    assert artifact.rows[1].raw_margin_value == -555555555
    assert artifact.upstream_content_hash == sha256_bytes(body)
    assert artifact.upstream_bytes == len(body)
    assert result.manifest.response_headers["x-civicdecision-upstream-bytes"] == str(len(body))
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.asyncio
async def test_census_tiger_connector_writes_one_boundary(tmp_path: Path) -> None:
    query = CensusPlaceQuery(state_fips="25", place_fips="07000")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_tiger_payload(query), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CensusTIGERPlaceConnector().fetch(query, tmp_path, client)
    assert result.manifest.record_count == 1
    assert "GEOID%3D%272507000%27" in str(result.manifest.data_url)
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"bad|header\n", "header has drifted"),
        (_population_table("1600000US2507000|1"), "malformed row"),
        (_population_table("1600000US2507000|not-int|1"), "integer encoded"),
        (_population_table("1600000US2507000|1|-1"), "unsupported special value"),
        (
            _population_table("1600000US2507000|1|1", "1600000US2507000|2|2"),
            "repeats a requested GEOID",
        ),
        (_population_table("1600000US9999999|1|1"), "lacks requested GEOIDs"),
    ],
)
@pytest.mark.asyncio
async def test_census_population_rejects_malformed_or_incomplete_tables(
    body: bytes, message: str, tmp_path: Path
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, request=request)

    query = CensusPopulationQuery(geoids=("2507000",))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await CensusACSPopulationTableConnector().fetch(query, tmp_path, client)


def test_census_population_contract_rejects_identity_tampering() -> None:
    with pytest.raises(ValidationError):
        CensusPopulationArtifact(
            source_id="wrong",  # type: ignore[arg-type]
            upstream_content_hash="sha256:" + "0" * 64,
            upstream_bytes=1,
            rows=[
                {
                    "geoid": "2507000",
                    "estimate": 1,
                    "margin_of_error_90": 1,
                    "raw_margin_value": 1,
                    "margin_status": "available",
                }
            ],
            transformation="filter",
            limitations=["test"],
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "FeatureCollection"),
        ({"type": "FeatureCollection", "features": []}, "exactly one"),
        (
            {
                "type": "FeatureCollection",
                "features": [{"properties": {"GEOID": "bad"}, "geometry": {}}],
            },
            "GEOID",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {"GEOID": "2507000"},
                        "geometry": {"type": "Point", "coordinates": [-71, 42]},
                    }
                ],
            },
            "polygonal",
        ),
    ],
)
@pytest.mark.asyncio
async def test_census_tiger_rejects_malformed_payloads(
    payload: object, message: str, tmp_path: Path
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    query = CensusPlaceQuery(state_fips="25", place_fips="07000")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await CensusTIGERPlaceConnector().fetch(query, tmp_path, client)


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ([[[-181, 42], [-70, 42], [-70, 43], [-181, 42]]], "outside"),
        ([[[-71, 42], [-70, 42], [-71, 42]]], "too few"),
        (["bad"], "nested shape"),
    ],
)
@pytest.mark.asyncio
async def test_census_tiger_rejects_invalid_geometry(
    coordinates: object, message: str, tmp_path: Path
) -> None:
    query = CensusPlaceQuery(state_fips="25", place_fips="07000")
    payload = _tiger_payload(query)
    payload["features"][0]["geometry"]["coordinates"] = coordinates  # type: ignore[index]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await CensusTIGERPlaceConnector().fetch(query, tmp_path, client)


def test_census_place_query_rejects_zero_codes_and_exposes_geoid() -> None:
    with pytest.raises(ValidationError, match="all-zero"):
        CensusPlaceQuery(state_fips="00", place_fips="07000")
    with pytest.raises(ValidationError, match="all-zero"):
        CensusPlaceQuery(state_fips="25", place_fips="00000")
    query = CensusPlaceQuery(state_fips="25", place_fips="07000")
    assert query.geoid == "2507000"
    assert query.tigerweb_parameters()["outSR"] == "4326"


def test_census_population_query_requires_sorted_unique_geoids() -> None:
    assert CensusPopulationQuery(geoids=("2507000", "3651000")).geoids == (
        "2507000",
        "3651000",
    )
    with pytest.raises(ValidationError, match="sorted and unique"):
        CensusPopulationQuery(geoids=("3651000", "2507000"))
    with pytest.raises(ValidationError, match="sorted and unique"):
        CensusPopulationQuery(geoids=("2507000", "2507000"))
    with pytest.raises(ValidationError, match="seven nonzero digits"):
        CensusPopulationQuery(geoids=("0000000",))
