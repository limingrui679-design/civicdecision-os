"""World Bank V2 Indicators API connector."""

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

WORLD_BANK_ENDPOINT = "https://api.worldbank.org/v2"
WORLD_BANK_DOCUMENTATION = "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"


class WorldBankIndicatorQuery(StrictModel):
    indicator: str = Field(pattern=r"^[A-Z0-9]+(?:\.[A-Z0-9]+)+$")
    country: str = Field(default="all", pattern=r"^(?:all|[A-Za-z0-9]{2,3})$")
    start_year: int = Field(ge=1960, le=2100)
    end_year: int = Field(ge=1960, le=2100)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=100, ge=1, le=1000)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return "all" if value.lower() == "all" else value.upper()

    @model_validator(mode="after")
    def ordered_years(self) -> WorldBankIndicatorQuery:
        if self.start_year > self.end_year:
            raise ValueError("start_year must not be later than end_year")
        return self

    def parameters(self) -> dict[str, str | int]:
        return {
            "date": f"{self.start_year}:{self.end_year}",
            "format": "json",
            "page": self.page,
            "per_page": self.per_page,
        }


class WorldBankIndicatorConnector:
    source_id = "world-bank-indicators-v2"

    async def fetch(
        self,
        query: WorldBankIndicatorQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=60,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        endpoint = f"{WORLD_BANK_ENDPOINT}/country/{query.country}/indicator/{query.indicator}"
        try:
            response = await client.get(endpoint, params=query.parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"World Bank request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("World Bank returned invalid JSON") from exc
        if not isinstance(payload, list) or len(payload) != 2:
            raise ConnectorError("World Bank payload must contain metadata and records")
        metadata, records = payload
        if not isinstance(metadata, dict) or not isinstance(records, list):
            raise ConnectorError("World Bank metadata or records have an unsafe shape")
        if not all(isinstance(record, dict) for record in records):
            raise ConnectorError("World Bank records must be objects")
        if len(records) > query.per_page:
            raise ConnectorError("World Bank returned more records than the declared page size")
        if metadata.get("page") != query.page:
            raise ConnectorError("World Bank response page does not match the requested page")

        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"world-bank-{query.indicator.lower()}-{query_key}.json"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        retrieved_at = datetime.now(UTC)
        last_updated = metadata.get("lastupdated")
        upstream_updated_at = None
        if isinstance(last_updated, str):
            try:
                upstream_updated_at = datetime.strptime(last_updated, "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
            except ValueError as exc:
                raise ConnectorError("World Bank lastupdated date is invalid") from exc
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"world-bank-{query_key}",
            name=f"World Bank indicator {query.indicator}",
            publisher="World Bank Group",
            landing_url=AnyHttpUrl(WORLD_BANK_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="CC BY 4.0 for World Bank-produced open data; verify indicator metadata",
            retrieved_at=retrieved_at,
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=len(records),
            schema_fingerprint=schema_fingerprint(records),
            geographic_scope=f"country={query.country}",
            temporal_scope=f"{query.start_year} through {query.end_year}",
            limitations=[
                "Indicators may be estimates, modeled values, or aggregates; inspect metadata.",
                "A bounded API page is not the complete indicator series.",
                "Cross-country comparability and revision behavior vary by indicator.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type"}
            },
        )
        manifest_path = output_dir / f"world-bank-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
