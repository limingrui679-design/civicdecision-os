"""USGS Earthquake Catalog connector."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USER_AGENT = "CivicDecisionOS/0.1 (open-source research connector)"


class USGSEarthquakeQuery(StrictModel):
    start: datetime
    end: datetime
    min_magnitude: float = Field(default=4.5, ge=-1, le=10)
    limit: int = Field(default=1000, ge=1, le=20_000)

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("USGS query times must include a timezone")
        return value

    @model_validator(mode="after")
    def ordered(self) -> USGSEarthquakeQuery:
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        return self

    def parameters(self) -> dict[str, str | int | float]:
        return {
            "format": "geojson",
            "starttime": self.start.isoformat().replace("+00:00", "Z"),
            "endtime": self.end.isoformat().replace("+00:00", "Z"),
            "minmagnitude": self.min_magnitude,
            "limit": self.limit,
            "orderby": "time-asc",
        }


class USGSEarthquakeConnector:
    source_id = "usgs-earthquakes"

    async def fetch(
        self,
        query: USGSEarthquakeQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=60, headers={"User-Agent": USER_AGENT})
        try:
            response = await client.get(USGS_ENDPOINT, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"USGS request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ConnectorError("USGS returned invalid JSON") from exc
        features = payload.get("features")
        if payload.get("type") != "FeatureCollection" or not isinstance(features, list):
            raise ConnectorError("USGS payload is not a GeoJSON FeatureCollection")
        if len(features) > query.limit:
            raise ConnectorError("USGS returned more records than the declared limit")
        if not all(isinstance(record, dict) for record in features):
            raise ConnectorError("USGS features must be objects")

        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"usgs-earthquakes-{query_key}.geojson"
        artifact_path = output_dir / artifact_name
        artifact_content = response.content
        atomic_write(artifact_path, artifact_content)

        retrieved_at = datetime.now(UTC)
        generated_ms = payload.get("metadata", {}).get("generated")
        upstream_updated_at = (
            datetime.fromtimestamp(generated_ms / 1000, tz=UTC)
            if isinstance(generated_ms, int)
            else None
        )
        relative_artifact = artifact_name
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"usgs-earthquakes-{query_key}",
            name="USGS Earthquake Catalog query",
            publisher="U.S. Geological Survey",
            landing_url=AnyHttpUrl("https://earthquake.usgs.gov/fdsnws/event/1/"),
            data_url=AnyHttpUrl(str(response.url)),
            license="U.S. government public data; check source terms and attribution guidance",
            retrieved_at=retrieved_at,
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=relative_artifact,
            content_hash=sha256_bytes(artifact_content),
            record_count=len(features),
            schema_fingerprint=schema_fingerprint(features),
            geographic_scope="Query-defined global earthquake catalog results",
            temporal_scope=f"{query.start.isoformat()} to {query.end.isoformat()}",
            limitations=[
                "Catalog records can be revised after retrieval.",
                "A bounded query is not the complete USGS earthquake catalog.",
                "Earthquake observations alone do not establish urban impact or causality.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"last-modified", "etag", "content-type"}
            },
        )
        manifest_path = output_dir / f"usgs-earthquakes-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
