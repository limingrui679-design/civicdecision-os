"""CDC PLACES census-tract connector."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import AnyHttpUrl, Field, field_validator

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

CDC_PLACES_ENDPOINT = "https://data.cdc.gov/resource/yjkw-uj5s.json"
CDC_PLACES_LANDING = (
    "https://data.cdc.gov/500-Cities-Places/"
    "PLACES-Census-Tract-Data-GIS-Friendly-Format-2025-/yjkw-uj5s"
)
DEFAULT_FIELDS = (
    "stateabbr,statedesc,countyname,countyfips,tractfips,totalpopulation,totalpop18plus,"
    "access2_crudeprev,casthma_crudeprev,copd_crudeprev,diabetes_crudeprev,"
    "ghlth_crudeprev,obesity_crudeprev,lacktrpt_crudeprev,geolocation"
)


class CDCPlacesQuery(StrictModel):
    state_abbr: str | None = None
    county_fips: str | None = None
    limit: int = Field(default=1000, ge=1, le=50_000)
    offset: int = Field(default=0, ge=0)

    @field_validator("state_abbr")
    @classmethod
    def valid_state(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("state_abbr must be a two-letter abbreviation")
        return value

    @field_validator("county_fips")
    @classmethod
    def valid_county(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 5 or not value.isdigit()):
            raise ValueError("county_fips must contain exactly five digits")
        return value

    def parameters(self) -> dict[str, str | int]:
        clauses: list[str] = []
        if self.state_abbr:
            clauses.append(f"stateabbr='{self.state_abbr}'")
        if self.county_fips:
            clauses.append(f"countyfips='{self.county_fips}'")
        parameters: dict[str, str | int] = {
            "$select": DEFAULT_FIELDS,
            "$limit": self.limit,
            "$offset": self.offset,
            "$order": "tractfips",
        }
        if clauses:
            parameters["$where"] = " AND ".join(clauses)
        return parameters


class CDCPlacesConnector:
    source_id = "cdc-places-2025-tract"

    async def fetch(
        self,
        query: CDCPlacesQuery,
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
            response = await client.get(CDC_PLACES_ENDPOINT, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"CDC PLACES request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: list[dict[str, Any]] = response.json()
        except ValueError as exc:
            raise ConnectorError("CDC PLACES returned invalid JSON") from exc
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ConnectorError("CDC PLACES payload must be a JSON array of objects")
        if len(payload) > query.limit:
            raise ConnectorError("CDC PLACES returned more records than the declared limit")

        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"cdc-places-{query_key}.json"
        artifact_path = output_dir / artifact_name
        artifact_content = response.content
        atomic_write(artifact_path, artifact_content)

        last_modified = response.headers.get("x-soda2-truth-last-modified")
        upstream_updated_at: datetime | None = None
        if last_modified:
            parsed = parsedate_to_datetime(last_modified)
            upstream_updated_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        retrieved_at = datetime.now(UTC)
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"cdc-places-{query_key}",
            name="CDC PLACES census-tract data, GIS-friendly 2025 release",
            publisher="U.S. Centers for Disease Control and Prevention",
            landing_url=AnyHttpUrl(CDC_PLACES_LANDING),
            data_url=AnyHttpUrl(str(response.url)),
            license="Public Domain; retain CDC attribution and methodology context",
            retrieved_at=retrieved_at,
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(artifact_content),
            record_count=len(payload),
            schema_fingerprint=schema_fingerprint(payload),
            geographic_scope=(
                f"state={query.state_abbr or 'ALL'}, county={query.county_fips or 'ALL'}"
            ),
            temporal_scope="CDC PLACES 2025 release using stated BRFSS/Census/ACS source years",
            limitations=[
                "PLACES values are model-based small-area estimates, not individual records.",
                "A limited API page is not the complete 83,522-tract dataset.",
                "Geographic estimates must not be interpreted as individual causal effects.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower()
                in {
                    "etag",
                    "last-modified",
                    "x-soda2-truth-last-modified",
                    "content-type",
                }
            },
        )
        manifest_path = output_dir / f"cdc-places-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
