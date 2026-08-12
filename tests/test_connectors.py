from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from civicdecision.connectors.base import atomic_write
from civicdecision.connectors.cdc_places import CDCPlacesConnector, CDCPlacesQuery
from civicdecision.connectors.usgs_earthquakes import (
    USGSEarthquakeConnector,
    USGSEarthquakeQuery,
)
from civicdecision.errors import ConnectorError


@pytest.mark.asyncio
async def test_usgs_connector_writes_verified_artifact(tmp_path: Path) -> None:
    payload = {
        "type": "FeatureCollection",
        "metadata": {"generated": 1_700_000_000_000},
        "features": [
            {
                "type": "Feature",
                "id": "event-1",
                "properties": {"mag": 5.1},
                "geometry": {"type": "Point", "coordinates": [1, 2, 3]},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request, headers={"ETag": "fixture"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await USGSEarthquakeConnector().fetch(
            USGSEarthquakeQuery(
                start=datetime(2020, 1, 1, tzinfo=UTC),
                end=datetime(2020, 1, 2, tzinfo=UTC),
                min_magnitude=5,
                limit=5,
            ),
            tmp_path,
            client,
        )
    assert result.manifest.record_count == 1
    assert json.loads(result.artifact_path.read_text())["features"][0]["id"] == "event-1"
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.asyncio
async def test_cdc_connector_writes_verified_artifact(tmp_path: Path) -> None:
    payload = [
        {
            "stateabbr": "MA",
            "tractfips": "25025000101",
            "totalpopulation": "1000",
            "diabetes_crudeprev": "8.0",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
            request=request,
            headers={"X-SODA2-Truth-Last-Modified": "Thu, 04 Dec 2025 10:40:53 GMT"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await CDCPlacesConnector().fetch(
            CDCPlacesQuery(state_abbr="MA", limit=5), tmp_path, client
        )
    assert result.manifest.record_count == 1
    assert result.manifest.query["state_abbr"] == "MA"
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.asyncio
async def test_connector_fails_safely_on_bad_payload(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="FeatureCollection"):
            await USGSEarthquakeConnector().fetch(
                USGSEarthquakeQuery(
                    start=datetime(2020, 1, 1, tzinfo=UTC),
                    end=datetime(2020, 1, 2, tzinfo=UTC),
                ),
                tmp_path,
                client,
            )


def test_query_validation_and_parameters() -> None:
    with pytest.raises(ValidationError, match="earlier than end"):
        USGSEarthquakeQuery(
            start=datetime(2020, 1, 2, tzinfo=UTC),
            end=datetime(2020, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match="timezone"):
        USGSEarthquakeQuery(start=datetime(2020, 1, 1), end=datetime(2020, 1, 2, tzinfo=UTC))
    with pytest.raises(ValidationError, match="two-letter"):
        CDCPlacesQuery(state_abbr="MASS")
    with pytest.raises(ValidationError, match="five digits"):
        CDCPlacesQuery(county_fips="123")
    query = CDCPlacesQuery(state_abbr="ma", county_fips="25025", limit=7, offset=2)
    assert query.state_abbr == "MA"
    assert query.parameters()["$where"] == "stateabbr='MA' AND countyfips='25025'"
    assert "$where" not in CDCPlacesQuery().parameters()


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_name", ["usgs", "cdc"])
async def test_connector_wraps_http_failures(tmp_path: Path, connector_name: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="request failed safely"):
            if connector_name == "usgs":
                await USGSEarthquakeConnector().fetch(
                    USGSEarthquakeQuery(
                        start=datetime(2020, 1, 1, tzinfo=UTC),
                        end=datetime(2020, 1, 2, tzinfo=UTC),
                    ),
                    tmp_path,
                    client,
                )
            else:
                await CDCPlacesConnector().fetch(CDCPlacesQuery(limit=1), tmp_path, client)


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_name", ["usgs", "cdc"])
async def test_connector_rejects_invalid_json(tmp_path: Path, connector_name: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="invalid JSON"):
            if connector_name == "usgs":
                await USGSEarthquakeConnector().fetch(
                    USGSEarthquakeQuery(
                        start=datetime(2020, 1, 1, tzinfo=UTC),
                        end=datetime(2020, 1, 2, tzinfo=UTC),
                    ),
                    tmp_path,
                    client,
                )
            else:
                await CDCPlacesConnector().fetch(CDCPlacesQuery(limit=1), tmp_path, client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"type": "FeatureCollection", "features": ["not-an-object"]}, "must be objects"),
        (
            {"type": "FeatureCollection", "features": [{"id": "1"}, {"id": "2"}]},
            "more records",
        ),
    ],
)
async def test_usgs_rejects_unsafe_feature_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await USGSEarthquakeConnector().fetch(
                USGSEarthquakeQuery(
                    start=datetime(2020, 1, 1, tzinfo=UTC),
                    end=datetime(2020, 1, 2, tzinfo=UTC),
                    limit=1,
                ),
                tmp_path,
                client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"not": "a-list"}, "array of objects"),
        (["not-an-object"], "array of objects"),
        ([{"id": "1"}, {"id": "2"}], "more records"),
    ],
)
async def test_cdc_rejects_unsafe_row_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await CDCPlacesConnector().fetch(CDCPlacesQuery(limit=1), tmp_path, client)


def test_atomic_write_cleans_temporary_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"fixture failure: {source} -> {destination}")

    monkeypatch.setattr("civicdecision.connectors.base.os.replace", fail_replace)
    target = tmp_path / "artifact.json"
    with pytest.raises(OSError, match="fixture failure"):
        atomic_write(target, b"payload")
    assert not list(tmp_path.glob(".*.tmp-*"))
