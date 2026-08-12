"""NASA POWER daily point-data connector."""

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
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

NASA_POWER_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_POWER_DOCUMENTATION = "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"


class PowerCommunity(StrEnum):
    RENEWABLE_ENERGY = "RE"
    SUSTAINABLE_BUILDINGS = "SB"
    AGROCLIMATOLOGY = "AG"


class PowerTimeStandard(StrEnum):
    UTC = "UTC"
    LOCAL_SOLAR_TIME = "LST"


class NASAPowerDailyQuery(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    start: date
    end: date
    parameters: tuple[str, ...] = ("T2M",)
    community: PowerCommunity = PowerCommunity.RENEWABLE_ENERGY
    time_standard: PowerTimeStandard = PowerTimeStandard.UTC

    @field_validator("parameters")
    @classmethod
    def valid_parameters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 20:
            raise ValueError("NASA POWER requires between one and twenty parameters")
        if len(set(value)) != len(value):
            raise ValueError("NASA POWER parameters must be unique")
        if any(not item.replace("_", "").isalnum() or item.upper() != item for item in value):
            raise ValueError("NASA POWER parameter names must use uppercase letters, digits, or _")
        return value

    @model_validator(mode="after")
    def bounded_window(self) -> NASAPowerDailyQuery:
        if self.start > self.end:
            raise ValueError("NASA POWER start must not be later than end")
        if (self.end - self.start).days > 366:
            raise ValueError("NASA POWER reference connector limits each request to 367 days")
        return self

    def parameters_dict(self) -> dict[str, str | float]:
        return {
            "parameters": ",".join(self.parameters),
            "community": self.community.value,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "start": self.start.strftime("%Y%m%d"),
            "end": self.end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": self.time_standard.value,
        }


class NASAPowerDailyConnector:
    source_id = "nasa-power-daily-point"

    async def fetch(
        self,
        query: NASAPowerDailyQuery,
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
            response = await client.get(NASA_POWER_ENDPOINT, params=query.parameters_dict())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"NASA POWER request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("NASA POWER returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("type") != "Feature":
            raise ConnectorError("NASA POWER payload must be a GeoJSON Feature")
        properties = payload.get("properties")
        if not isinstance(properties, dict) or not isinstance(properties.get("parameter"), dict):
            raise ConnectorError("NASA POWER payload lacks parameter time series")
        parameter_data = properties["parameter"]
        flattened: list[dict[str, Any]] = []
        for parameter in query.parameters:
            series = parameter_data.get(parameter)
            if not isinstance(series, dict):
                raise ConnectorError(f"NASA POWER payload lacks requested parameter {parameter}")
            for day, value in series.items():
                if not isinstance(day, str) or not isinstance(value, int | float):
                    raise ConnectorError(
                        "NASA POWER observations require date keys and numeric values"
                    )
                flattened.append({"parameter": parameter, "date": day, "value": value})
        maximum_observations = len(query.parameters) * ((query.end - query.start).days + 1)
        if len(flattened) > maximum_observations:
            raise ConnectorError("NASA POWER returned more observations than the declared window")

        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"nasa-power-{query_key}.geojson"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        header_value = payload.get("header")
        header: dict[str, Any] = header_value if isinstance(header_value, dict) else {}
        api_value = header.get("api")
        api: dict[str, Any] = api_value if isinstance(api_value, dict) else {}
        api_version = api.get("version", "unknown")
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"nasa-power-{query_key}",
            name=f"NASA POWER daily point data ({api_version})",
            publisher="NASA Langley Research Center POWER Project",
            landing_url=AnyHttpUrl(NASA_POWER_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="NASA Earth science public data; retain POWER citation and access metadata",
            retrieved_at=datetime.now(UTC),
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=len(flattened),
            schema_fingerprint=schema_fingerprint(flattened),
            geographic_scope=f"point=({query.latitude},{query.longitude})",
            temporal_scope=f"{query.start.isoformat()} through {query.end.isoformat()}",
            limitations=[
                "POWER values are gridded analysis-ready products, not station observations.",
                "Near-real-time meteorology can be replaced by improved products after retrieval.",
                "One point does not characterize within-city microclimate or exposure.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type"}
            },
        )
        manifest_path = output_dir / f"nasa-power-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
