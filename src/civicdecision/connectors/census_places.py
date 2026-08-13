"""U.S. Census ACS place profiles and TIGERweb incorporated-place boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import AnyHttpUrl, Field, model_validator

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

ACS_POPULATION_TABLE_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/2024/"
    "table-based-SF/data/5YRData/acsdt5y2024-b01003.dat"
)
ACS_SUMMARY_DOCUMENTATION = "https://www.census.gov/programs-surveys/acs/data/summary-file.html"
TIGERWEB_ENDPOINT = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query"
)
TIGERWEB_DOCUMENTATION = "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_restmapservice.html"
TIGERWEB_FIELDS = "GEOID,BASENAME,NAME,STATE,PLACE,AREALAND,AREAWATER,LSADC,FUNCSTAT"


class CensusPlaceQuery(StrictModel):
    state_fips: str = Field(pattern=r"^[0-9]{2}$")
    place_fips: str = Field(pattern=r"^[0-9]{5}$")

    @model_validator(mode="after")
    def nonzero(self) -> CensusPlaceQuery:
        if self.state_fips == "00" or self.place_fips == "00000":
            raise ValueError("Census place identifiers cannot use all-zero codes")
        return self

    @property
    def geoid(self) -> str:
        return f"{self.state_fips}{self.place_fips}"

    def tigerweb_parameters(self) -> dict[str, str]:
        return {
            "where": f"GEOID='{self.geoid}'",
            "outFields": TIGERWEB_FIELDS,
            "returnGeometry": "true",
            "outSR": "4326",
            "geometryPrecision": "5",
            "f": "geojson",
        }


class CensusPopulationQuery(StrictModel):
    geoids: tuple[str, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def sorted_unique_geoids(self) -> CensusPopulationQuery:
        if any(len(item) != 7 or not item.isdigit() or item == "0000000" for item in self.geoids):
            raise ValueError("Census population GEOIDs must be seven nonzero digits")
        if list(self.geoids) != sorted(set(self.geoids)):
            raise ValueError("Census population GEOIDs must be sorted and unique")
        return self


class ACSMarginStatus(StrEnum):
    AVAILABLE = "available"
    CONTROLLED = "controlled"


class CensusPopulationRow(StrictModel):
    geoid: str = Field(pattern=r"^[0-9]{7}$")
    estimate: int = Field(ge=0)
    margin_of_error_90: int = Field(ge=0)
    raw_margin_value: int
    margin_status: ACSMarginStatus

    @model_validator(mode="after")
    def margin_semantics(self) -> CensusPopulationRow:
        if self.raw_margin_value == -555555555:
            if self.margin_status is not ACSMarginStatus.CONTROLLED or self.margin_of_error_90 != 0:
                raise ValueError("controlled ACS population estimates must use zero effective MOE")
        elif (
            self.raw_margin_value < 0
            or self.margin_status is not ACSMarginStatus.AVAILABLE
            or self.margin_of_error_90 != self.raw_margin_value
        ):
            raise ValueError("available ACS population MOE must preserve its raw value")
        return self


class CensusPopulationArtifact(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    source_id: Literal["census-acs5-2024-b01003-population"] = "census-acs5-2024-b01003-population"
    vintage: Literal[2024] = 2024
    table_id: Literal["B01003"] = "B01003"
    universe: Literal["Total population"] = "Total population"
    upstream_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    upstream_bytes: int = Field(ge=1)
    rows: list[CensusPopulationRow] = Field(min_length=1)
    transformation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def artifact_integrity(self) -> CensusPopulationArtifact:
        geoids = [item.geoid for item in self.rows]
        if geoids != sorted(set(geoids)):
            raise ValueError("Census population artifact GEOIDs must be sorted and unique")
        return self


class CensusACSPopulationTableConnector:
    """Filter named incorporated-place rows from the official no-key B01003 file."""

    source_id = "census-acs5-2024-b01003-population"

    async def fetch(
        self,
        query: CensusPopulationQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = _client()
        try:
            response = await client.get(ACS_POPULATION_TABLE_URL)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(
                f"Census ACS population-table request failed safely: {exc}"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        if len(response.content) > 25 * 1024 * 1024:
            raise ConnectorError("Census ACS population table exceeds the 25 MiB safety bound")
        try:
            lines = response.content.decode("utf-8-sig").splitlines()
        except UnicodeDecodeError as exc:
            raise ConnectorError("Census ACS population table is not valid UTF-8") from exc
        if not lines or lines[0] != "GEO_ID|B01003_E001|B01003_M001":
            raise ConnectorError("Census ACS population table header has drifted")
        targets = {f"1600000US{geoid}": geoid for geoid in query.geoids}
        rows: list[CensusPopulationRow] = []
        seen: set[str] = set()
        for line in lines[1:]:
            parts = line.split("|")
            if len(parts) != 3:
                raise ConnectorError("Census ACS population table contains a malformed row")
            if parts[0] not in targets:
                continue
            geoid = targets[parts[0]]
            if geoid in seen:
                raise ConnectorError("Census ACS population table repeats a requested GEOID")
            try:
                estimate = int(parts[1])
                raw_margin = int(parts[2])
            except ValueError as exc:
                raise ConnectorError("Census ACS population row is not integer encoded") from exc
            if raw_margin == -555555555:
                status = ACSMarginStatus.CONTROLLED
                margin = 0
            elif raw_margin >= 0:
                status = ACSMarginStatus.AVAILABLE
                margin = raw_margin
            else:
                raise ConnectorError("Census ACS population row uses an unsupported special value")
            rows.append(
                CensusPopulationRow(
                    geoid=geoid,
                    estimate=estimate,
                    margin_of_error_90=margin,
                    raw_margin_value=raw_margin,
                    margin_status=status,
                )
            )
            seen.add(geoid)
        rows.sort(key=lambda item: item.geoid)
        if seen != set(query.geoids):
            missing = sorted(set(query.geoids) - seen)
            raise ConnectorError(f"Census ACS population table lacks requested GEOIDs: {missing}")
        artifact = CensusPopulationArtifact(
            upstream_content_hash=sha256_bytes(response.content),
            upstream_bytes=len(response.content),
            rows=rows,
            transformation=(
                "Selected exact 1600000US place GEO_ID rows from B01003, preserved estimates and "
                "raw margins, and mapped -555555555 controlled margins to effective zero."
            ),
            limitations=[
                "B01003 is a place-level total population estimate, not an individual record.",
                "A controlled margin is treated as zero only under published Census guidance.",
                "The five-year estimate pools survey responses and should not be called a 2024 "
                "point-in-time count.",
            ],
        )
        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        stem = f"census-acs5-2024-b01003-{query_key}"
        artifact_name = f"{stem}.json"
        artifact_path = output_dir / artifact_name
        content = canonical_json(artifact) + b"\n"
        atomic_write(artifact_path, content)
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=stem,
            name="ACS 2024 five-year B01003 population rows for Tier-D places",
            publisher="U.S. Census Bureau",
            landing_url=AnyHttpUrl(ACS_SUMMARY_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="U.S. Census Bureau public data; source attribution requested",
            retrieved_at=datetime.now(UTC),
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(content),
            record_count=len(rows),
            schema_fingerprint=schema_fingerprint([item.model_dump(mode="json") for item in rows]),
            geographic_scope=f"Census incorporated-place GEOIDs: {','.join(query.geoids)}",
            temporal_scope="2024 ACS five-year estimates",
            limitations=artifact.limitations,
            response_headers={
                **{
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() in {"content-type", "etag", "last-modified"}
                },
                "x-civicdecision-upstream-sha256": artifact.upstream_content_hash,
                "x-civicdecision-upstream-bytes": str(artifact.upstream_bytes),
            },
        )
        manifest_path = output_dir / f"{stem}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=120,
        headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
    )


def _coordinate_count(value: Any) -> int:
    if isinstance(value, list):
        if len(value) == 2 and all(isinstance(item, int | float) for item in value):
            longitude, latitude = (float(item) for item in value)
            if not isfinite(longitude) or not isfinite(latitude):
                raise ConnectorError("TIGERweb boundary contains non-finite coordinates")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ConnectorError("TIGERweb boundary coordinate is outside EPSG:4326")
            return 1
        return sum(_coordinate_count(item) for item in value)
    raise ConnectorError("TIGERweb boundary coordinates have an invalid nested shape")


class CensusTIGERPlaceConnector:
    source_id = "census-tigerweb-current-incorporated-place"

    async def fetch(
        self,
        query: CensusPlaceQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = _client()
        try:
            response = await client.get(TIGERWEB_ENDPOINT, params=query.tigerweb_parameters())
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"Census TIGERweb place request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        if len(response.content) > 10 * 1024 * 1024:
            raise ConnectorError("Census TIGERweb place response exceeds the 10 MiB safety bound")
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ConnectorError("Census TIGERweb endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ConnectorError("Census TIGERweb payload must be a GeoJSON FeatureCollection")
        features = payload.get("features")
        if (
            not isinstance(features, list)
            or len(features) != 1
            or not isinstance(features[0], dict)
        ):
            raise ConnectorError("Census TIGERweb query must return exactly one place feature")
        feature = features[0]
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or properties.get("GEOID") != query.geoid:
            raise ConnectorError("Census TIGERweb feature GEOID does not match the query")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") not in {"Polygon", "MultiPolygon"}
            or "coordinates" not in geometry
        ):
            raise ConnectorError("Census TIGERweb place must contain polygonal geometry")
        vertices = _coordinate_count(geometry["coordinates"])
        if vertices < 4:
            raise ConnectorError("Census TIGERweb polygon contains too few coordinate vertices")
        stem = f"census-tigerweb-place-{query.geoid}"
        artifact_name = f"{stem}.geojson"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        fingerprint_record = {
            **properties,
            "geometry_type": geometry["type"],
            "coordinate_vertices": vertices,
        }
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=stem,
            name=f"TIGERweb incorporated-place boundary: {properties.get('NAME', query.geoid)}",
            publisher="U.S. Census Bureau Geography Division",
            landing_url=AnyHttpUrl(TIGERWEB_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="U.S. Census Bureau public geographic data; source attribution requested",
            retrieved_at=datetime.now(UTC),
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=1,
            schema_fingerprint=schema_fingerprint([fingerprint_record]),
            geographic_scope=f"Incorporated place GEOID {query.geoid}",
            temporal_scope="TIGERweb current service vintage at retrieval",
            limitations=[
                "Legal boundary vintages can change through annexation and boundary surveys.",
                "A municipal polygon does not define neighborhoods, service areas, or exposure.",
                "Coordinate precision was requested at five decimal places for a bounded sample.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"content-type", "etag", "last-modified"}
            },
        )
        manifest_path = output_dir / f"{stem}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )


__all__ = [
    "ACSMarginStatus",
    "CensusACSPopulationTableConnector",
    "CensusPlaceQuery",
    "CensusPopulationArtifact",
    "CensusPopulationQuery",
    "CensusPopulationRow",
    "CensusTIGERPlaceConnector",
]
