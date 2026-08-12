"""GeoNames downloadable city-gazetteer connector with ZIP safety gates."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx
from pydantic import AnyHttpUrl, Field

from civicdecision.connectors.base import FetchResult, atomic_write, write_manifest
from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import (
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.source import SourceManifest

GEONAMES_CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
GEONAMES_DOCUMENTATION = "https://download.geonames.org/export/dump/"
GEONAMES_MEMBER = "cities15000.txt"
GEONAMES_COLUMNS = (
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
)


class GeoNamesCitiesQuery(StrictModel):
    dataset: str = Field(default="cities15000", pattern=r"^cities15000$")
    max_compressed_bytes: int = Field(default=10_000_000, ge=1_000_000, le=50_000_000)
    max_uncompressed_bytes: int = Field(default=25_000_000, ge=5_000_000, le=100_000_000)


def validate_geonames_zip(content: bytes, query: GeoNamesCitiesQuery) -> tuple[int, bytes]:
    """Validate archive paths, sizes, CRC, encoding, and the 19-column row contract."""

    if len(content) > query.max_compressed_bytes:
        raise ConnectorError("GeoNames archive exceeds the declared compressed-size limit")
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != GEONAMES_MEMBER:
                raise ConnectorError("GeoNames archive must contain only cities15000.txt")
            member = members[0]
            if member.is_dir() or member.file_size > query.max_uncompressed_bytes:
                raise ConnectorError("GeoNames member exceeds the declared uncompressed-size limit")
            if Path(member.filename).is_absolute() or ".." in Path(member.filename).parts:
                raise ConnectorError("GeoNames archive contains an unsafe member path")
            extracted = archive.read(member)
    except BadZipFile as exc:
        raise ConnectorError("GeoNames returned an invalid ZIP archive") from exc
    try:
        text = extracted.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConnectorError("GeoNames city file is not valid UTF-8") from exc
    rows = [line for line in text.splitlines() if line]
    if not rows:
        raise ConnectorError("GeoNames city file is empty")
    if any(len(row.split("\t")) != len(GEONAMES_COLUMNS) for row in rows):
        raise ConnectorError("GeoNames city rows must contain exactly 19 columns")
    return len(rows), extracted


class GeoNamesCitiesConnector:
    source_id = "geonames-cities15000"

    async def fetch(
        self,
        query: GeoNamesCitiesQuery,
        output_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> FetchResult:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=120,
                headers={"User-Agent": "CivicDecisionOS/0.1 (open-source research connector)"},
            )
        try:
            response = await client.get(GEONAMES_CITIES_URL)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ConnectorError(f"GeoNames request failed safely: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        record_count, extracted = validate_geonames_zip(response.content, query)
        query_key = sha256_bytes(canonical_json(query.model_dump(mode="json")))[7:19]
        artifact_name = f"geonames-cities15000-{query_key}.zip"
        artifact_path = output_dir / artifact_name
        atomic_write(artifact_path, response.content)
        last_modified = response.headers.get("last-modified")
        upstream_updated_at = None
        if last_modified:
            try:
                parsed = parsedate_to_datetime(last_modified)
                upstream_updated_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError) as exc:
                raise ConnectorError("GeoNames Last-Modified header is invalid") from exc
        first_values = extracted.splitlines()[0].decode("utf-8").split("\t")
        schema_record = dict(zip(GEONAMES_COLUMNS, first_values, strict=True))
        manifest = SourceManifest(
            source_id=self.source_id,
            artifact_id=f"geonames-cities15000-{query_key}",
            name="GeoNames cities15000 gazetteer extract",
            publisher="GeoNames",
            landing_url=AnyHttpUrl(GEONAMES_DOCUMENTATION),
            data_url=AnyHttpUrl(str(response.url)),
            license="Creative Commons Attribution 4.0; attribution to GeoNames required",
            retrieved_at=datetime.now(UTC),
            upstream_updated_at=upstream_updated_at,
            query=query.model_dump(mode="json"),
            artifact_path=artifact_name,
            content_hash=sha256_bytes(response.content),
            record_count=record_count,
            schema_fingerprint=schema_fingerprint([schema_record]),
            geographic_scope="Worldwide populated places in the cities15000 extract",
            temporal_scope=(
                "Current GeoNames extract as of the recorded modification/retrieval time"
            ),
            limitations=[
                "GeoNames aggregates many sources and provides no warranty of accuracy "
                "or completeness.",
                "Population and administrative attributes may use different source years "
                "or definitions.",
                "The gazetteer contains points, not official municipal boundaries or "
                "service areas.",
            ],
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"etag", "last-modified", "content-type", "content-length"}
            },
        )
        manifest_path = output_dir / f"geonames-cities15000-{query_key}.manifest.json"
        write_manifest(manifest_path, manifest)
        return FetchResult(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
