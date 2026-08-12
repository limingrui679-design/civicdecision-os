from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from civicdecision.connectors.eurostat import (
    EurostatStatisticsConnector,
    EurostatStatisticsQuery,
)
from civicdecision.connectors.nasa_power import (
    NASAPowerDailyConnector,
    NASAPowerDailyQuery,
)
from civicdecision.connectors.nyc_311 import NYC311Connector, NYC311Query
from civicdecision.connectors.open_fema import (
    OpenFEMADisasterConnector,
    OpenFEMADisasterQuery,
)
from civicdecision.connectors.registry import (
    CONNECTOR_REGISTRY,
    connector_descriptor,
    registry_json,
)
from civicdecision.connectors.world_bank import (
    WorldBankIndicatorConnector,
    WorldBankIndicatorQuery,
)
from civicdecision.errors import ConnectorError


def response(payload: Any, request: httpx.Request, **headers: str) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request, headers=headers)


@pytest.mark.asyncio
async def test_world_bank_connector_writes_verified_page(tmp_path: Path) -> None:
    payload = [
        {"page": 1, "pages": 1, "per_page": 2, "total": 1, "lastupdated": "2025-01-02"},
        [
            {
                "indicator": {"id": "SP.POP.TOTL", "value": "Population"},
                "country": {"id": "US", "value": "United States"},
                "date": "2023",
                "value": 1,
            }
        ],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request, ETag="fixture")

    query = WorldBankIndicatorQuery(
        indicator="SP.POP.TOTL",
        country="us",
        start_year=2023,
        end_year=2023,
        per_page=2,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await WorldBankIndicatorConnector().fetch(query, tmp_path, client)
    assert query.country == "US"
    assert result.manifest.record_count == 1
    assert result.manifest.upstream_updated_at == datetime(2025, 1, 2, tzinfo=UTC)
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "metadata and records"),
        ([[], []], "unsafe shape"),
        ([{"page": 1}, ["row"]], "must be objects"),
        ([{"page": 1}, [{}, {}]], "more records"),
        ([{"page": 2}, []], "does not match"),
        ([{"page": 1, "lastupdated": "bad"}, []], "lastupdated"),
    ],
)
@pytest.mark.asyncio
async def test_world_bank_rejects_unsafe_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request)

    query = WorldBankIndicatorQuery(
        indicator="SP.POP.TOTL", start_year=2023, end_year=2023, per_page=1
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await WorldBankIndicatorConnector().fetch(query, tmp_path, client)


def test_world_bank_query_rejects_reversed_years() -> None:
    with pytest.raises(ValidationError, match="start_year"):
        WorldBankIndicatorQuery(indicator="SP.POP.TOTL", start_year=2024, end_year=2023)
    query = WorldBankIndicatorQuery(
        indicator="SP.POP.TOTL", country="ALL", start_year=2023, end_year=2023
    )
    assert query.country == "all"
    assert query.parameters()["date"] == "2023:2023"


def nasa_payload() -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-71, 42, 1]},
        "properties": {"parameter": {"T2M": {"20200101": 1.5, "20200102": 2.5}}},
        "header": {"api": {"version": "v2.9.6"}},
    }


@pytest.mark.asyncio
async def test_nasa_power_connector_writes_verified_observations(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(nasa_payload(), request)

    query = NASAPowerDailyQuery(
        latitude=42,
        longitude=-71,
        start=date(2020, 1, 1),
        end=date(2020, 1, 2),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await NASAPowerDailyConnector().fetch(query, tmp_path, client)
    assert result.manifest.record_count == 2
    assert "v2.9.6" in result.manifest.name
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "GeoJSON Feature"),
        ({"type": "Feature", "properties": {}}, "parameter time series"),
        (
            {"type": "Feature", "properties": {"parameter": {}}},
            "lacks requested parameter",
        ),
        (
            {
                "type": "Feature",
                "properties": {"parameter": {"T2M": {"bad": "not-numeric"}}},
            },
            "date keys and numeric",
        ),
        (
            {
                "type": "Feature",
                "properties": {"parameter": {"T2M": {"20200101": 1, "20200102": 2}}},
            },
            "more observations",
        ),
    ],
)
@pytest.mark.asyncio
async def test_nasa_power_rejects_unsafe_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request)

    query = NASAPowerDailyQuery(
        latitude=0,
        longitude=0,
        start=date(2020, 1, 1),
        end=date(2020, 1, 1),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await NASAPowerDailyConnector().fetch(query, tmp_path, client)


def test_nasa_power_query_gates() -> None:
    base = {"latitude": 0, "longitude": 0, "start": date(2020, 1, 1), "end": date(2020, 1, 2)}
    with pytest.raises(ValidationError, match="one and twenty"):
        NASAPowerDailyQuery(**base, parameters=())
    with pytest.raises(ValidationError, match="unique"):
        NASAPowerDailyQuery(**base, parameters=("T2M", "T2M"))
    with pytest.raises(ValidationError, match="uppercase"):
        NASAPowerDailyQuery(**base, parameters=("t2m",))
    with pytest.raises(ValidationError, match="not be later"):
        NASAPowerDailyQuery(**{**base, "start": date(2020, 1, 3)})
    with pytest.raises(ValidationError, match="367 days"):
        NASAPowerDailyQuery(**{**base, "end": date(2022, 1, 1)})
    assert NASAPowerDailyQuery(**base).parameters_dict()["format"] == "JSON"


def fema_payload() -> dict[str, object]:
    return {
        "metadata": {"top": 2, "skip": 0},
        "DisasterDeclarationsSummaries": [
            {
                "id": "a",
                "state": "MA",
                "incidentType": "Flood",
                "lastRefresh": "2025-01-02T03:04:05.000Z",
            }
        ],
    }


@pytest.mark.asyncio
async def test_openfema_connector_writes_verified_page(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(fema_payload(), request)

    query = OpenFEMADisasterQuery(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 1, tzinfo=UTC),
        state="ma",
        incident_type="Flood",
        top=2,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenFEMADisasterConnector().fetch(query, tmp_path, client)
    assert query.state == "MA"
    assert "state eq 'MA'" in str(query.parameters()["$filter"])
    assert result.manifest.record_count == 1
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "declarations array"),
        ({"DisasterDeclarationsSummaries": ["bad"], "metadata": {}}, "must be objects"),
        (
            {"DisasterDeclarationsSummaries": [{}, {}], "metadata": {}},
            "more records",
        ),
        ({"DisasterDeclarationsSummaries": [], "metadata": []}, "request metadata"),
        (
            {
                "DisasterDeclarationsSummaries": [{"lastRefresh": "bad"}],
                "metadata": {},
            },
            "lastRefresh",
        ),
    ],
)
@pytest.mark.asyncio
async def test_openfema_rejects_unsafe_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request)

    query = OpenFEMADisasterQuery(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 1, tzinfo=UTC),
        top=1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await OpenFEMADisasterConnector().fetch(query, tmp_path, client)


def test_openfema_query_gates_and_escaping() -> None:
    with pytest.raises(ValidationError, match="two-letter"):
        OpenFEMADisasterQuery(
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, tzinfo=UTC),
            state="Mass",
        )
    with pytest.raises(ValidationError, match="earlier"):
        OpenFEMADisasterQuery(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, tzinfo=UTC),
        )
    query = OpenFEMADisasterQuery(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 1, tzinfo=UTC),
        incident_type="Director's test",
    )
    assert "Director''s" in str(query.parameters()["$filter"])


def eurostat_payload() -> dict[str, object]:
    return {
        "version": "2.0",
        "class": "dataset",
        "label": "Fixture",
        "updated": "2025-01-02T03:04:05+0000",
        "id": ["freq", "geo", "time"],
        "size": [1, 1, 2],
        "value": {"0": 1.0, "1": 2.0},
        "dimension": {},
    }


@pytest.mark.asyncio
async def test_eurostat_connector_writes_verified_subset(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(eurostat_payload(), request)

    query = EurostatStatisticsQuery(
        dataset="demo_gind", filters={"geo": "DE", "time": "2023"}, max_cells=2
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await EurostatStatisticsConnector().fetch(query, tmp_path, client)
    assert result.manifest.record_count == 2
    assert query.parameters()["lang"] == "en"
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "JSON-stat dataset"),
        ({"class": "dataset", "id": [], "size": [1], "value": {}}, "structure"),
        (
            {"class": "dataset", "id": ["x"], "size": [2], "value": {"0": 1}},
            "cell limit",
        ),
        (
            {"class": "dataset", "id": ["x"], "size": [1], "value": {"0": "bad"}},
            "numeric or null",
        ),
        (
            {
                "class": "dataset",
                "id": ["x"],
                "size": [1],
                "value": {},
                "updated": "bad",
            },
            "updated timestamp",
        ),
    ],
)
@pytest.mark.asyncio
async def test_eurostat_rejects_unsafe_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request)

    query = EurostatStatisticsQuery(dataset="fixture", filters={"geo": "DE"}, max_cells=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await EurostatStatisticsConnector().fetch(query, tmp_path, client)


def test_eurostat_filters_require_nonempty_values() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        EurostatStatisticsQuery(dataset="fixture", filters={"geo": ""})


def nyc_payload() -> list[dict[str, str]]:
    return [
        {
            "unique_key": "1",
            "created_date": "2024-01-01T00:00:00.000",
            "agency": "DOT",
            "complaint_type": "Street Condition",
        }
    ]


@pytest.mark.asyncio
async def test_nyc_311_connector_writes_verified_page(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(nyc_payload(), request)

    query = NYC311Query(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
        borough="queens",
        agency="dot",
        limit=2,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await NYC311Connector().fetch(query, tmp_path, client)
    assert query.borough == "QUEENS"
    assert "agency = 'DOT'" in str(query.parameters()["$where"])
    assert result.manifest.record_count == 1
    result.manifest.verify_artifact(tmp_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "array of objects"),
        ([{}, {}], "more records"),
        ([{"unique_key": "1"}], "require unique_key"),
    ],
)
@pytest.mark.asyncio
async def test_nyc_311_rejects_unsafe_payloads(
    tmp_path: Path, payload: object, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(payload, request)

    query = NYC311Query(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
        limit=1,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await NYC311Connector().fetch(query, tmp_path, client)


def test_nyc_query_gates() -> None:
    with pytest.raises(ValidationError, match="recognized borough"):
        NYC311Query(
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
            borough="Boston",
        )
    with pytest.raises(ValidationError, match="earlier"):
        NYC311Query(
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 1, tzinfo=UTC),
        )


Fetcher = Callable[[httpx.AsyncClient, Path], Awaitable[object]]


def new_connector_fetchers() -> list[Fetcher]:
    async def world_bank(client: httpx.AsyncClient, path: Path) -> object:
        return await WorldBankIndicatorConnector().fetch(
            WorldBankIndicatorQuery(indicator="SP.POP.TOTL", start_year=2023, end_year=2023),
            path,
            client,
        )

    async def nasa(client: httpx.AsyncClient, path: Path) -> object:
        return await NASAPowerDailyConnector().fetch(
            NASAPowerDailyQuery(
                latitude=0,
                longitude=0,
                start=date(2020, 1, 1),
                end=date(2020, 1, 1),
            ),
            path,
            client,
        )

    async def fema(client: httpx.AsyncClient, path: Path) -> object:
        return await OpenFEMADisasterConnector().fetch(
            OpenFEMADisasterQuery(
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2025, 1, 1, tzinfo=UTC),
            ),
            path,
            client,
        )

    async def eurostat(client: httpx.AsyncClient, path: Path) -> object:
        return await EurostatStatisticsConnector().fetch(
            EurostatStatisticsQuery(dataset="fixture", filters={"geo": "DE"}),
            path,
            client,
        )

    async def nyc(client: httpx.AsyncClient, path: Path) -> object:
        return await NYC311Connector().fetch(
            NYC311Query(
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 2, tzinfo=UTC),
            ),
            path,
            client,
        )

    return [world_bank, nasa, fema, eurostat, nyc]


@pytest.mark.parametrize("fetcher", new_connector_fetchers())
@pytest.mark.asyncio
async def test_new_connectors_wrap_http_and_json_failures(tmp_path: Path, fetcher: Fetcher) -> None:
    def http_failure(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(http_failure)) as client:
        with pytest.raises(ConnectorError, match="request failed safely"):
            await fetcher(client, tmp_path)

    def invalid_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid_json)) as client:
        with pytest.raises(ConnectorError, match="invalid JSON"):
            await fetcher(client, tmp_path)


def test_connector_registry_is_unique_loadable_and_deterministic() -> None:
    ids = [item.id for item in CONNECTOR_REGISTRY]
    assert len(ids) == 7
    assert len(ids) == len(set(ids))
    assert json.loads(registry_json())[0]["id"] == ids[0]
    assert connector_descriptor("nasa-power-daily-point").scope.value == "global"
    with pytest.raises(ConnectorError, match="unknown connector"):
        connector_descriptor("does-not-exist")
