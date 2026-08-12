"""Eurostat Statistics API JSON-stat connector."""

from __future__ import annotations

from datetime import UTC, datetime
from math import prod
from pathlib import Path
from typing import Any

import httpx
from pydantic import AnyHttpUrl, Field, field_validator

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    JsonValue,
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

EUROSTAT_ENDPOINT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
EUROSTAT_DOCUMENTATION = (
    "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction"
)


class EurostatStatisticsQuery(StrictModel):
    dataset: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    filters: dict[str, str] = Field(min_length=1)
    language: str = Field(default="en", pattern=r"^(?:en|fr|de)$")
    max_cells: int = Field(default=1000, ge=1, le=100_000)

    @field_validator("filters")
    @classmethod
    def valid_filters(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key or not item for key, item in value.items()):
            raise ValueError("Eurostat filters require non-empty keys and values")
        return value

    def parameters(self) -> dict[str, str]:
        return {"lang": self.language, **self.filters}


class EurostatStatisticsConnector:
    source_id = "eurostat-statistics-api"

    async def fetch(
        self,
        query: EurostatStatisticsQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=90,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        endpoint = f"{EUROSTAT_ENDPOINT}/{query.dataset}"
        try:
            response = await client.get(endpoint, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"Eurostat request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("Eurostat returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("class") != "dataset":
            raise ConnectorError("Eurostat payload must be a JSON-stat dataset")
        dimensions = payload.get("id")
        sizes = payload.get("size")
        values = payload.get("value")
        if (
            not isinstance(dimensions, list)
            or not all(isinstance(item, str) for item in dimensions)
            or not isinstance(sizes, list)
            or not all(isinstance(item, int) and item >= 0 for item in sizes)
            or len(dimensions) != len(sizes)
            or not isinstance(values, dict)
        ):
            raise ConnectorError("Eurostat JSON-stat structure is invalid")
        declared_cells = prod(sizes)
        if declared_cells > query.max_cells:
            raise ConnectorError("Eurostat response exceeds the declared cell limit")
        if any(not isinstance(value, int | float | None) for value in values.values()):
            raise ConnectorError("Eurostat values must be numeric or null")
        non_null_values = [value for value in values.values() if value is not None]
        fingerprint_records: list[dict[str, JsonValue]] = [
            {"dimension": dimension, "size": size}
            for dimension, size in zip(dimensions, sizes, strict=True)
        ]
        fingerprint_records.append({"metric": "non_null_values", "count": len(non_null_values)})

        updated = payload.get("updated")
        upstream_updated_at = None
        if isinstance(updated, str):
            try:
                upstream_updated_at = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError as exc:
                raise ConnectorError("Eurostat updated timestamp is invalid") from exc
        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"eurostat-{query.dataset.lower()}-{query_key}.json"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"eurostat-{query_key}",
            name=f"Eurostat dataset {query.dataset}",
            publisher="European Commission, Eurostat",
            landing_url=AnyHttpUrl(EUROSTAT_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="Eurostat free reuse with source acknowledgement; dataset exceptions may apply",
            retrieved_at=datetime.now(UTC),
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=len(non_null_values),
            schema_fingerprint=schema_fingerprint(fingerprint_records),
            geographic_scope=f"filters={query.filters}",
            temporal_scope=f"filters={query.filters}",
            limitations=[
                "Eurostat exposes the latest dataset version and does not preserve "
                "prior API versions.",
                "Status flags and dataset metadata are required for substantive interpretation.",
                "Some third-party or non-European data have additional reuse restrictions.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type"}
            },
        )
        manifest_path = output_dir / f"eurostat-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
