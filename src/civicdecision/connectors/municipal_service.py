"""Bounded municipal service-request aggregation across audited public platforms.

The connector intentionally stores aggregate rows rather than street addresses or free-form
request text.  This keeps the public reference corpus small enough to rebuild, removes fields
that can contain personal information, and still preserves the temporal, categorical, spatial,
and workflow evidence needed by the Tier-D compiler.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest


class MunicipalPlatform(StrEnum):
    SOCRATA = "socrata"
    CKAN_DATASTORE = "ckan-datastore"
    CARTO_SQL = "carto-sql"


class MunicipalAggregation(StrEnum):
    DAILY_CATEGORY = "daily-category"
    DAILY_AREA = "daily-area"
    CATEGORY_STATUS = "category-status"
    AREA_STATUS = "area-status"


class MunicipalFieldMap(StrictModel):
    opened_at: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    category: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    area: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    status: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class MunicipalDatasetSpec(StrictModel):
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    publisher: str = Field(min_length=1)
    platform: MunicipalPlatform
    endpoint: AnyHttpUrl
    landing_url: AnyHttpUrl
    dataset_identifier: str = Field(min_length=1)
    fields: MunicipalFieldMap
    license_summary: str = Field(min_length=1)
    request_semantics: str = Field(min_length=1)
    primary_limitations: list[str] = Field(min_length=1)


class MunicipalServiceQuery(StrictModel):
    start: date
    end: date
    aggregation: MunicipalAggregation
    limit: int = Field(default=50_000, ge=1, le=50_000)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def ordered_and_bounded(self) -> MunicipalServiceQuery:
        if self.start >= self.end:
            raise ValueError("municipal query start must be earlier than end")
        if (self.end - self.start).days > 366:
            raise ValueError("municipal query window cannot exceed 366 days")
        return self


class MunicipalAggregateRow(StrictModel):
    service_date: date | None = None
    category: str | None = None
    area: str | None = None
    status: str | None = None
    request_count: int = Field(ge=1)

    @field_validator("category", "area", "status", mode="before")
    @classmethod
    def preserve_missing_dimension(cls, value: Any) -> str | None:
        if value is None:
            return None
        if str(value).strip() == "":
            return "(missing)"
        return str(value)


class MunicipalAggregateArtifact(StrictModel):
    schema_version: str = "1.0.0"
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    platform: MunicipalPlatform
    dataset_identifier: str = Field(min_length=1)
    aggregation: MunicipalAggregation
    coverage_start: date
    coverage_end_exclusive: date
    rows: list[MunicipalAggregateRow] = Field(min_length=1)
    aggregate_row_count: int = Field(ge=1)
    underlying_request_count: int = Field(ge=1)
    transformation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def artifact_integrity(self) -> MunicipalAggregateArtifact:
        if self.coverage_start >= self.coverage_end_exclusive:
            raise ValueError("municipal artifact coverage must be ordered")
        if self.aggregate_row_count != len(self.rows):
            raise ValueError("municipal aggregate row count must match serialized rows")
        if self.underlying_request_count != sum(row.request_count for row in self.rows):
            raise ValueError("municipal underlying request count must reconcile to aggregate rows")
        dimensions = {
            MunicipalAggregation.DAILY_CATEGORY: ("service_date", "category"),
            MunicipalAggregation.DAILY_AREA: ("service_date", "area"),
            MunicipalAggregation.CATEGORY_STATUS: ("category", "status"),
            MunicipalAggregation.AREA_STATUS: ("area", "status"),
        }[self.aggregation]
        keys: list[tuple[object, ...]] = []
        for row in self.rows:
            if any(getattr(row, field) is None for field in dimensions):
                raise ValueError("municipal aggregate row lacks a required dimension")
            forbidden = {"service_date", "category", "area", "status"} - set(dimensions)
            if any(getattr(row, field) is not None for field in forbidden):
                raise ValueError("municipal aggregate row contains an undeclared dimension")
            keys.append(tuple(getattr(row, field) for field in dimensions))
        if keys != sorted(keys, key=lambda item: tuple(str(value) for value in item)):
            raise ValueError("municipal aggregate rows must use deterministic dimension order")
        if len(keys) != len(set(keys)):
            raise ValueError("municipal aggregate dimension keys must be unique")
        return self


def _dimensions(
    spec: MunicipalDatasetSpec, aggregation: MunicipalAggregation
) -> list[tuple[str, str]]:
    fields = spec.fields
    mapping = {
        MunicipalAggregation.DAILY_CATEGORY: [
            (fields.opened_at, "service_date"),
            (fields.category, "category"),
        ],
        MunicipalAggregation.DAILY_AREA: [
            (fields.opened_at, "service_date"),
            (fields.area, "area"),
        ],
        MunicipalAggregation.CATEGORY_STATUS: [
            (fields.category, "category"),
            (fields.status, "status"),
        ],
        MunicipalAggregation.AREA_STATUS: [(fields.area, "area"), (fields.status, "status")],
    }
    return mapping[aggregation]


def _literal(value: date) -> str:
    return value.isoformat().replace("'", "''")


def _socrata_parameters(
    spec: MunicipalDatasetSpec, query: MunicipalServiceQuery
) -> dict[str, str | int]:
    dimensions = _dimensions(spec, query.aggregation)
    expressions = []
    groups = []
    for field, alias in dimensions:
        expression = f"date_trunc_ymd({field})" if alias == "service_date" else field
        expressions.append(f"{expression} as {alias}")
        groups.append(expression)
    opened = spec.fields.opened_at
    where = (
        f"{opened} >= '{_literal(query.start)}T00:00:00' AND "
        f"{opened} < '{_literal(query.end)}T00:00:00'"
    )
    aliases = ",".join(alias for _, alias in dimensions)
    return {
        "$select": f"{','.join(expressions)},count(*) as request_count",
        "$where": where,
        "$group": ",".join(groups),
        "$order": aliases,
        "$limit": query.limit,
        "$offset": query.offset,
    }


def _sql(spec: MunicipalDatasetSpec, query: MunicipalServiceQuery) -> str:
    fields = spec.fields
    table = spec.dataset_identifier
    dimensions = _dimensions(spec, query.aggregation)
    if spec.platform is MunicipalPlatform.CKAN_DATASTORE:
        quoted_table = f'"{table}"'

        def field_expression(field: str) -> str:
            return f'"{field}"'

        def date_expression(field: str) -> str:
            return f"date_trunc('day', {field_expression(field)}::timestamp)::date"

    else:
        quoted_table = table

        def field_expression(field: str) -> str:
            return field

        def date_expression(field: str) -> str:
            return f"date_trunc('day', {field})::date"

    selected = []
    grouped = []
    ordered = []
    for field, alias in dimensions:
        expression = date_expression(field) if alias == "service_date" else field_expression(field)
        selected.append(f"{expression} AS {alias}")
        grouped.append(expression)
        ordered.append(alias)
    opened = field_expression(fields.opened_at)
    return (
        f"SELECT {', '.join(selected)}, count(*)::int AS request_count "
        f"FROM {quoted_table} WHERE {opened} >= '{_literal(query.start)}' "
        f"AND {opened} < '{_literal(query.end)}' GROUP BY {', '.join(grouped)} "
        f"ORDER BY {', '.join(ordered)} LIMIT {query.limit} OFFSET {query.offset}"
    )


def _parameters(spec: MunicipalDatasetSpec, query: MunicipalServiceQuery) -> dict[str, str | int]:
    if spec.platform is MunicipalPlatform.SOCRATA:
        return _socrata_parameters(spec, query)
    statement = _sql(spec, query)
    if spec.platform is MunicipalPlatform.CKAN_DATASTORE:
        return {"sql": statement}
    return {"q": statement}


def _payload_rows(spec: MunicipalDatasetSpec, payload: Any) -> list[dict[str, Any]]:
    rows: Any
    if spec.platform is MunicipalPlatform.SOCRATA:
        rows = payload
    elif spec.platform is MunicipalPlatform.CKAN_DATASTORE:
        rows = payload.get("result", {}).get("records") if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("success") is not True:
            raise ConnectorError("municipal CKAN response did not report success")
    else:
        rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ConnectorError("municipal response does not contain an aggregate row list")
    return rows


def _dimension_value(raw: dict[str, Any], field: str) -> Any:
    value = raw.get(field)
    return "(missing)" if value is None or str(value).strip() == "" else value


def _normalize_rows(
    raw_rows: list[dict[str, Any]], aggregation: MunicipalAggregation
) -> list[MunicipalAggregateRow]:
    required = {
        MunicipalAggregation.DAILY_CATEGORY: ("service_date", "category"),
        MunicipalAggregation.DAILY_AREA: ("service_date", "area"),
        MunicipalAggregation.CATEGORY_STATUS: ("category", "status"),
        MunicipalAggregation.AREA_STATUS: ("area", "status"),
    }[aggregation]
    rows: list[MunicipalAggregateRow] = []
    for raw in raw_rows:
        if "request_count" not in raw:
            raise ConnectorError("municipal aggregate row is missing its count")
        try:
            rows.append(
                MunicipalAggregateRow(
                    service_date=raw.get("service_date"),
                    category=(
                        _dimension_value(raw, "category") if "category" in required else None
                    ),
                    area=_dimension_value(raw, "area") if "area" in required else None,
                    status=_dimension_value(raw, "status") if "status" in required else None,
                    request_count=int(raw["request_count"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ConnectorError("municipal aggregate row contains an invalid value") from exc
    if len(rows) == 0:
        raise ConnectorError("municipal query returned no aggregate rows")
    consolidated: dict[tuple[object, ...], int] = {}
    for row in rows:
        key = tuple(getattr(row, field) for field in required)
        consolidated[key] = consolidated.get(key, 0) + row.request_count
    rows = [
        MunicipalAggregateRow.model_validate(
            {
                **{field: key[index] for index, field in enumerate(required)},
                "request_count": request_count,
            }
        )
        for key, request_count in consolidated.items()
    ]
    rows.sort(key=lambda row: tuple(str(getattr(row, field)) for field in required))
    if len(rows) >= 50_000:
        raise ConnectorError(
            "municipal aggregate reached the 50,000-row safety boundary; narrow the window"
        )
    return rows


class MunicipalServiceConnector:
    """Fetch one bounded aggregate for a registered municipal dataset."""

    def __init__(self, spec: MunicipalDatasetSpec) -> None:
        self.spec = spec
        self.source_id = spec.source_id

    async def fetch(
        self,
        query: MunicipalServiceQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=180,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        try:
            response = await client.get(
                str(self.spec.endpoint), params=_parameters(self.spec, query)
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(
                f"{self.spec.city_name} municipal request failed safely: {exc}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("municipal endpoint returned invalid JSON") from exc
        raw_rows = _payload_rows(self.spec, payload)
        if len(raw_rows) > query.limit:
            raise ConnectorError("municipal endpoint returned more rows than the declared limit")
        rows = _normalize_rows(raw_rows, query.aggregation)
        artifact = MunicipalAggregateArtifact(
            source_id=self.spec.source_id,
            city_id=self.spec.city_id,
            platform=self.spec.platform,
            dataset_identifier=self.spec.dataset_identifier,
            aggregation=query.aggregation,
            coverage_start=query.start,
            coverage_end_exclusive=query.end,
            rows=rows,
            aggregate_row_count=len(rows),
            underlying_request_count=sum(row.request_count for row in rows),
            transformation=(
                "Official endpoint-side grouped count; client normalized aliases, missing "
                "dimensions, integer counts, row order, and canonical JSON only."
            ),
            limitations=self.spec.primary_limitations,
        )
        stem = municipal_artifact_stem(self.spec.city_id, query)
        artifact_name = f"{stem}.json"
        artifact_path = output_dir / artifact_name
        content = canonical_json(artifact)
        atomic_write(artifact_path, content + b"\n")
        manifest = SourceManifest(
            source_id=self.spec.source_id,
            artifact_id=stem,
            name=f"{self.spec.city_name} service requests: {query.aggregation.value}",
            publisher=self.spec.publisher,
            landing_url=self.spec.landing_url,
            data_url=AnyHttpUrl(str(response.url)),
            license=self.spec.license_summary,
            retrieved_at=datetime.now(UTC),
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(content + b"\n"),
            record_count=len(rows),
            schema_fingerprint=schema_fingerprint(
                [row.model_dump(mode="json", exclude_none=True) for row in rows]
            ),
            geographic_scope=self.spec.city_name,
            temporal_scope=f"[{query.start.isoformat()}, {query.end.isoformat()})",
            limitations=self.spec.primary_limitations,
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower()
                in {
                    "content-type",
                    "etag",
                    "last-modified",
                    "x-soda2-truth-last-modified",
                }
            },
        )
        manifest_path = output_dir / f"{stem}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )


def municipal_artifact_stem(city_id: str, query: MunicipalServiceQuery) -> str:
    """Return the deterministic aggregate artifact stem for resumable acquisition."""

    query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
    return f"{city_id}.{query.aggregation.value}.{query_key}"


__all__ = [
    "MunicipalAggregateArtifact",
    "MunicipalAggregateRow",
    "MunicipalAggregation",
    "MunicipalDatasetSpec",
    "MunicipalFieldMap",
    "MunicipalPlatform",
    "MunicipalServiceConnector",
    "MunicipalServiceQuery",
    "municipal_artifact_stem",
]
