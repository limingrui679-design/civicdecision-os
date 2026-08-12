"""NYC Open Data 311 Service Requests connector."""

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
    ensure_aware,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

NYC_311_ENDPOINT = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
NYC_311_LANDING = (
    "https://data.cityofnewyork.us/Social-Services/"
    "311-Service-Requests-from-2020-to-Present/erm2-nwe9"
)
NYC_311_FIELDS = (
    "unique_key,created_date,closed_date,agency,agency_name,complaint_type,descriptor,"
    "location_type,incident_zip,borough,status,resolution_description,latitude,longitude"
)


class NYC311Query(StrictModel):
    start: datetime
    end: datetime
    borough: str | None = None
    agency: str | None = Field(default=None, min_length=1, max_length=20)
    limit: int = Field(default=1000, ge=1, le=50_000)
    offset: int = Field(default=0, ge=0)

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "NYC 311 query datetime")

    @field_validator("borough")
    @classmethod
    def normalize_borough(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.upper()
        allowed = {"BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"}
        if normalized not in allowed:
            raise ValueError("NYC 311 borough must be a recognized borough")
        return normalized

    @model_validator(mode="after")
    def ordered(self) -> NYC311Query:
        if self.start >= self.end:
            raise ValueError("NYC 311 start must be earlier than end")
        return self

    @staticmethod
    def _socrata_datetime(value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    def parameters(self) -> dict[str, str | int]:
        clauses = [
            f"created_date >= '{self._socrata_datetime(self.start)}'",
            f"created_date < '{self._socrata_datetime(self.end)}'",
        ]
        if self.borough:
            clauses.append(f"borough = '{self.borough}'")
        if self.agency:
            escaped = self.agency.upper().replace("'", "''")
            clauses.append(f"agency = '{escaped}'")
        return {
            "$select": NYC_311_FIELDS,
            "$where": " AND ".join(clauses),
            "$order": "created_date,unique_key",
            "$limit": self.limit,
            "$offset": self.offset,
        }


class NYC311Connector:
    source_id = "nyc-open-data-311-2020-present"

    async def fetch(
        self,
        query: NYC311Query,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=90,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        try:
            response = await client.get(NYC_311_ENDPOINT, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"NYC 311 request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("NYC 311 returned invalid JSON") from exc
        if not isinstance(payload, list) or not all(isinstance(record, dict) for record in payload):
            raise ConnectorError("NYC 311 payload must be an array of objects")
        if len(payload) > query.limit:
            raise ConnectorError("NYC 311 returned more records than the declared limit")
        if any("unique_key" not in record or "created_date" not in record for record in payload):
            raise ConnectorError("NYC 311 records require unique_key and created_date")

        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"nyc-311-{query_key}.json"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"nyc-311-{query_key}",
            name="NYC 311 Service Requests from 2020 to Present",
            publisher="City of New York",
            landing_url=AnyHttpUrl(NYC_311_LANDING),
            data_url=AnyHttpUrl(str(response.url)),
            license="NYC Open Data terms; public resource with dataset-specific terms if present",
            retrieved_at=datetime.now(UTC),
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=len(payload),
            schema_fingerprint=schema_fingerprint(payload),
            geographic_scope=f"New York City, borough={query.borough or 'ALL'}",
            temporal_scope=f"created from {query.start.isoformat()} to {query.end.isoformat()}",
            limitations=[
                "A service request is a report, not a verified incident or measured "
                "service outcome.",
                "Reporting propensity, access, duplicates, and agency practices create "
                "selection effects.",
                "Records can be corrected or overwritten and the portal does not retain "
                "all prior versions.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower()
                in {"etag", "last-modified", "x-soda2-truth-last-modified", "content-type"}
            },
        )
        manifest_path = output_dir / f"nyc-311-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
