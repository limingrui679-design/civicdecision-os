"""OpenFEMA Disaster Declarations Summaries V2 connector."""

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

OPEN_FEMA_ENDPOINT = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
OPEN_FEMA_DOCUMENTATION = "https://www.fema.gov/about/openfema"
RECORD_KEY = "DisasterDeclarationsSummaries"


class OpenFEMADisasterQuery(StrictModel):
    start: datetime
    end: datetime
    state: str | None = None
    incident_type: str | None = Field(default=None, min_length=1, max_length=80)
    top: int = Field(default=100, ge=1, le=1000)
    skip: int = Field(default=0, ge=0)

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "OpenFEMA query datetime")

    @field_validator("state")
    @classmethod
    def valid_state(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("OpenFEMA state must be a two-letter abbreviation")
        return value

    @model_validator(mode="after")
    def ordered(self) -> OpenFEMADisasterQuery:
        if self.start >= self.end:
            raise ValueError("OpenFEMA start must be earlier than end")
        return self

    @staticmethod
    def _fema_datetime(value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000z")

    def parameters(self) -> dict[str, str | int]:
        clauses = [
            f"declarationDate ge '{self._fema_datetime(self.start)}'",
            f"declarationDate lt '{self._fema_datetime(self.end)}'",
        ]
        if self.state:
            clauses.append(f"state eq '{self.state}'")
        if self.incident_type:
            escaped = self.incident_type.replace("'", "''")
            clauses.append(f"incidentType eq '{escaped}'")
        return {
            "$filter": " and ".join(clauses),
            "$orderby": "id",
            "$top": self.top,
            "$skip": self.skip,
        }


class OpenFEMADisasterConnector:
    source_id = "openfema-disaster-declarations-v2"

    async def fetch(
        self,
        query: OpenFEMADisasterQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=60,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        try:
            response = await client.get(OPEN_FEMA_ENDPOINT, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"OpenFEMA request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("OpenFEMA returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get(RECORD_KEY), list):
            raise ConnectorError("OpenFEMA payload lacks the declarations array")
        records = payload[RECORD_KEY]
        if not all(isinstance(record, dict) for record in records):
            raise ConnectorError("OpenFEMA declaration records must be objects")
        if len(records) > query.top:
            raise ConnectorError("OpenFEMA returned more records than the declared limit")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ConnectorError("OpenFEMA payload lacks request metadata")

        last_refresh_values = [
            record.get("lastRefresh")
            for record in records
            if isinstance(record.get("lastRefresh"), str)
        ]
        upstream_updated_at = None
        if last_refresh_values:
            try:
                upstream_updated_at = max(
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    for value in last_refresh_values
                )
            except ValueError as exc:
                raise ConnectorError("OpenFEMA lastRefresh timestamp is invalid") from exc
        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"openfema-disasters-{query_key}.json"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"openfema-disasters-{query_key}",
            name="OpenFEMA Disaster Declarations Summaries V2",
            publisher="U.S. Federal Emergency Management Agency",
            landing_url=AnyHttpUrl(OPEN_FEMA_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="U.S. federal open data subject to FEMA.gov and OpenFEMA terms",
            retrieved_at=datetime.now(UTC),
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=len(records),
            schema_fingerprint=schema_fingerprint(records),
            geographic_scope=f"state={query.state or 'ALL'}",
            temporal_scope=(
                f"declarations from {query.start.isoformat()} to {query.end.isoformat()}"
            ),
            limitations=[
                "A declaration record does not measure damages, recovery, or intervention effects.",
                "Records may be amended after retrieval and place coverage can be non-uniform.",
                "A bounded page is not the complete disaster declaration history.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type"}
            },
        )
        manifest_path = output_dir / f"openfema-disasters-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
