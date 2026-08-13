from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from civicdecision.connectors.municipal_service import (
    MunicipalAggregateArtifact,
    MunicipalAggregation,
    MunicipalDatasetSpec,
    MunicipalPlatform,
    MunicipalServiceConnector,
    MunicipalServiceQuery,
)
from civicdecision.deep.specs import DEEP_CITY_SPECS
from civicdecision.errors import ConnectorError
from civicdecision.io import validate_document
from civicdecision.protocols.source import SourceManifest


def _response_payload(platform: MunicipalPlatform) -> object:
    rows = [
        {"service_date": "2025-04-01", "category": "Pothole", "request_count": "4"},
        {"service_date": "2025-04-02", "category": None, "request_count": 2},
    ]
    if platform is MunicipalPlatform.SOCRATA:
        return rows
    if platform is MunicipalPlatform.CKAN_DATASTORE:
        return {"success": True, "result": {"records": rows}}
    return {"rows": rows, "total_rows": 2}


def _spec(platform: MunicipalPlatform) -> MunicipalDatasetSpec:
    return next(item.source for item in DEEP_CITY_SPECS if item.source.platform is platform)


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", list(MunicipalPlatform))
async def test_municipal_connector_writes_canonical_private_safe_artifact(
    platform: MunicipalPlatform, tmp_path: Path
) -> None:
    request_url: str | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_url
        request_url = str(request.url)
        return httpx.Response(200, json=_response_payload(platform), request=request)

    spec = _spec(platform)
    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
        limit=100,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MunicipalServiceConnector(spec).fetch(query, tmp_path, client)

    artifact = MunicipalAggregateArtifact.model_validate_json(result.artifact_path.read_bytes())
    manifest = validate_document(result.manifest_path, SourceManifest)
    manifest.verify_artifact(tmp_path)
    assert artifact.aggregate_row_count == 2
    assert artifact.underlying_request_count == 6
    assert artifact.rows[1].category == "(missing)"
    assert manifest.record_count == 2
    assert request_url is not None
    if platform is MunicipalPlatform.SOCRATA:
        assert "%24select=" in request_url
        assert "count%28%2A%29" in request_url
    elif platform is MunicipalPlatform.CKAN_DATASTORE:
        assert "sql=" in request_url
        assert "%22open_dt%22" in request_url
    else:
        assert "q=" in request_url
        assert "public_cases_fc" in request_url
    row_keys = set().union(
        *(row.model_dump(mode="json", exclude_none=True) for row in artifact.rows)
    )
    assert row_keys <= {"service_date", "category", "area", "status", "request_count"}
    assert not {"address", "description", "latitude", "longitude"} & row_keys


@pytest.mark.parametrize("aggregation", list(MunicipalAggregation))
def test_all_aggregation_dimensions_generate_queries(aggregation: MunicipalAggregation) -> None:
    from civicdecision.connectors import municipal_service

    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 5, 1),
        aggregation=aggregation,
    )
    for platform in MunicipalPlatform:
        parameters = municipal_service._parameters(_spec(platform), query)
        rendered = " ".join(str(value) for value in parameters.values())
        assert "request_count" in rendered
        assert "2025-04-01" in rendered
        assert "2025-05-01" in rendered


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2025-04-01", "2025-04-01", "earlier"),
        ("2025-04-02", "2025-04-01", "earlier"),
        ("2024-01-01", "2025-01-02", "366"),
    ],
)
def test_municipal_query_rejects_invalid_windows(start: str, end: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        MunicipalServiceQuery.model_validate(
            {
                "start": start,
                "end": end,
                "aggregation": MunicipalAggregation.DAILY_AREA,
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"not": "a row list"}, "row list"),
        ([{"service_date": "2025-04-01", "category": "x"}], "missing its count"),
        ([{"service_date": "2025-04-01", "category": "x", "request_count": "bad"}], "invalid"),
        ([], "no aggregate"),
    ],
)
async def test_municipal_connector_rejects_malformed_socrata_payloads(
    payload: object, message: str, tmp_path: Path
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match=message):
            await MunicipalServiceConnector(_spec(MunicipalPlatform.SOCRATA)).fetch(
                query, tmp_path, client
            )


@pytest.mark.asyncio
async def test_municipal_connector_rejects_ckan_failure(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False}, request=request)

    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="did not report success"):
            await MunicipalServiceConnector(_spec(MunicipalPlatform.CKAN_DATASTORE)).fetch(
                query, tmp_path, client
            )


@pytest.mark.asyncio
async def test_municipal_connector_wraps_http_and_json_errors(tmp_path: Path) -> None:
    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )

    async def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(ConnectorError, match="failed safely"):
            await MunicipalServiceConnector(_spec(MunicipalPlatform.SOCRATA)).fetch(
                query, tmp_path, client
            )

    async def invalid_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid_json)) as client:
        with pytest.raises(ConnectorError, match="invalid JSON"):
            await MunicipalServiceConnector(_spec(MunicipalPlatform.SOCRATA)).fetch(
                query, tmp_path, client
            )


def test_municipal_aggregate_contract_rejects_tampered_counts_and_dimensions() -> None:
    payload = {
        "source_id": "test-source",
        "city_id": "test-city",
        "platform": "socrata",
        "dataset_identifier": "test",
        "aggregation": "daily-category",
        "coverage_start": "2025-04-01",
        "coverage_end_exclusive": "2025-04-03",
        "rows": [
            {"service_date": "2025-04-01", "category": "a", "request_count": 2},
            {"service_date": "2025-04-02", "category": "b", "request_count": 3},
        ],
        "aggregate_row_count": 2,
        "underlying_request_count": 5,
        "transformation": "test aggregation",
        "limitations": ["test only"],
    }
    MunicipalAggregateArtifact.model_validate(payload)

    tampered = json.loads(json.dumps(payload))
    tampered["underlying_request_count"] = 6
    with pytest.raises(ValidationError, match="reconcile"):
        MunicipalAggregateArtifact.model_validate(tampered)

    tampered = json.loads(json.dumps(payload))
    tampered["aggregate_row_count"] = 3
    with pytest.raises(ValidationError, match="serialized rows"):
        MunicipalAggregateArtifact.model_validate(tampered)

    tampered = json.loads(json.dumps(payload))
    tampered["rows"][0]["status"] = "open"
    with pytest.raises(ValidationError, match="undeclared dimension"):
        MunicipalAggregateArtifact.model_validate(tampered)

    tampered = json.loads(json.dumps(payload))
    tampered["rows"].reverse()
    with pytest.raises(ValidationError, match="deterministic"):
        MunicipalAggregateArtifact.model_validate(tampered)

    tampered = json.loads(json.dumps(payload))
    tampered["rows"][1] = tampered["rows"][0]
    tampered["underlying_request_count"] = 4
    with pytest.raises(ValidationError, match="unique"):
        MunicipalAggregateArtifact.model_validate(tampered)


def test_normalization_consolidates_dimensions_that_match_after_whitespace_cleanup() -> None:
    from civicdecision.connectors import municipal_service

    rows = municipal_service._normalize_rows(
        [
            {"category": "Pothole", "status": "Open", "request_count": 2},
            {"category": " Pothole ", "status": "Open ", "request_count": "3"},
        ],
        MunicipalAggregation.CATEGORY_STATUS,
    )
    assert len(rows) == 1
    assert rows[0].category == "Pothole"
    assert rows[0].request_count == 5


def test_deep_city_source_specs_are_unique_and_heterogeneous() -> None:
    assert len(DEEP_CITY_SPECS) == 8
    assert [item.selection_order for item in DEEP_CITY_SPECS] == list(range(1, 9))
    assert len({item.city_id for item in DEEP_CITY_SPECS}) == 8
    assert len({item.source.source_id for item in DEEP_CITY_SPECS}) == 8
    assert {item.source.platform for item in DEEP_CITY_SPECS} == set(MunicipalPlatform)
    assert all(item.source.primary_limitations for item in DEEP_CITY_SPECS)
