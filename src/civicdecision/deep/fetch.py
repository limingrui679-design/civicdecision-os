"""Acquire the bounded official municipal evidence used by the Tier-D reference build."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from pydantic import Field, ValidationError

from civicdecision.connectors.base import FetchResult
from civicdecision.connectors.census_places import (
    CensusACSPopulationTableConnector,
    CensusPlaceQuery,
    CensusPopulationQuery,
    CensusTIGERPlaceConnector,
)
from civicdecision.connectors.municipal_service import (
    MunicipalAggregateArtifact,
    MunicipalAggregation,
    MunicipalServiceConnector,
    MunicipalServiceQuery,
    municipal_artifact_stem,
)
from civicdecision.connectors.nasa_power import (
    NASAPowerDailyConnector,
    NASAPowerDailyQuery,
)
from civicdecision.deep.specs import DEEP_CITY_SPECS
from civicdecision.errors import CivicDecisionError, ConnectorError
from civicdecision.protocols.base import StrictModel, canonical_json, sha256_bytes
from civicdecision.protocols.source import SourceManifest


class TierDSourceFetchReport(StrictModel):
    city_count: int = Field(ge=1)
    aggregation_count: int = Field(ge=1)
    artifact_paths: list[Path] = Field(min_length=1)
    manifest_paths: list[Path] = Field(min_length=1)
    aggregate_rows: int = Field(ge=1)


class TierDContextFetchReport(StrictModel):
    city_count: int = Field(ge=1)
    artifact_count: int = Field(ge=1)
    artifact_paths: list[Path] = Field(min_length=1)
    manifest_paths: list[Path] = Field(min_length=1)
    declared_source_units: int = Field(ge=1)


async def _fetch_with_retry(
    *,
    connector: MunicipalServiceConnector,
    query: MunicipalServiceQuery,
    output_dir: Path,
    attempts: int,
) -> FetchResult:
    last_error: ConnectorError | None = None
    for attempt in range(attempts):
        try:
            return await connector.fetch(query, output_dir)
        except ConnectorError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def _resume_result(
    *,
    connector: MunicipalServiceConnector,
    query: MunicipalServiceQuery,
    output_dir: Path,
) -> FetchResult | None:
    stem = municipal_artifact_stem(connector.spec.city_id, query)
    artifact_path = output_dir / f"{stem}.json"
    manifest_path = output_dir / f"{stem}.manifest.json"
    try:
        manifest = SourceManifest.model_validate_json(manifest_path.read_bytes())
        manifest.verify_artifact(output_dir)
        artifact = MunicipalAggregateArtifact.model_validate_json(artifact_path.read_bytes())
    except (OSError, ValidationError, CivicDecisionError):
        return None
    if (
        manifest.source_id != connector.spec.source_id
        or artifact.source_id != connector.spec.source_id
        or artifact.city_id != connector.spec.city_id
        or artifact.aggregation is not query.aggregation
        or artifact.coverage_start != query.start
        or artifact.coverage_end_exclusive != query.end
        or manifest.record_count != artifact.aggregate_row_count
    ):
        return None
    return FetchResult(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest=manifest,
        warnings=["Verified and reused an existing source artifact."],
    )


def _resume_named(
    *, output_dir: Path, stem: str, suffix: str, source_id: str
) -> FetchResult | None:
    artifact_path = output_dir / f"{stem}{suffix}"
    manifest_path = output_dir / f"{stem}.manifest.json"
    try:
        manifest = SourceManifest.model_validate_json(manifest_path.read_bytes())
        manifest.verify_artifact(output_dir)
    except (OSError, ValidationError, CivicDecisionError):
        return None
    if manifest.source_id != source_id or manifest.artifact_path != artifact_path.name:
        return None
    return FetchResult(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest=manifest,
        warnings=["Verified and reused an existing source artifact."],
    )


async def fetch_tier_d_sources(
    output_dir: Path,
    *,
    start: date = date(2025, 4, 1),
    end: date = date(2025, 10, 1),
    attempts: int = 3,
    concurrency: int = 2,
    resume: bool = True,
) -> TierDSourceFetchReport:
    """Fetch four privacy-minimized official aggregate views for all eight cities."""

    if attempts < 1:
        raise ValueError("Tier-D source fetch requires at least one attempt")
    if concurrency < 1 or concurrency > 8:
        raise ValueError("Tier-D source fetch concurrency must be between one and eight")
    semaphore = asyncio.Semaphore(concurrency)

    async def one(city_index: int, aggregation: MunicipalAggregation) -> FetchResult:
        spec = DEEP_CITY_SPECS[city_index]
        query = MunicipalServiceQuery(start=start, end=end, aggregation=aggregation)
        destination = output_dir / spec.city_id
        connector = MunicipalServiceConnector(spec.source)
        if (
            resume
            and (
                existing := _resume_result(connector=connector, query=query, output_dir=destination)
            )
            is not None
        ):
            return existing
        async with semaphore:
            return await _fetch_with_retry(
                connector=connector,
                query=query,
                output_dir=destination,
                attempts=attempts,
            )

    tasks = [
        one(city_index, aggregation)
        for city_index in range(len(DEEP_CITY_SPECS))
        for aggregation in MunicipalAggregation
    ]
    results = await asyncio.gather(*tasks)
    ordered = sorted(results, key=lambda item: item.artifact_path.as_posix())
    return TierDSourceFetchReport(
        city_count=len(DEEP_CITY_SPECS),
        aggregation_count=len(ordered),
        artifact_paths=[item.artifact_path for item in ordered],
        manifest_paths=[item.manifest_path for item in ordered],
        aggregate_rows=sum(item.manifest.record_count for item in ordered),
    )


async def fetch_tier_d_context(
    output_dir: Path,
    *,
    start: date = date(2025, 4, 1),
    end_inclusive: date = date(2025, 9, 30),
    attempts: int = 3,
    concurrency: int = 2,
    resume: bool = True,
) -> TierDContextFetchReport:
    """Fetch an ACS profile, legal boundary, and climate point for every Tier-D city."""

    if attempts < 1:
        raise ValueError("Tier-D context fetch requires at least one attempt")
    if concurrency < 1 or concurrency > 8:
        raise ValueError("Tier-D context fetch concurrency must be between one and eight")
    semaphore = asyncio.Semaphore(concurrency)
    population_query = CensusPopulationQuery(
        geoids=tuple(
            sorted(f"{spec.census_state_fips}{spec.census_place_fips}" for spec in DEEP_CITY_SPECS)
        )
    )

    async def population() -> FetchResult:
        connector = CensusACSPopulationTableConnector()
        query_key = sha256_bytes(canonical_json(population_query.model_dump(mode="json")))[7:19]
        stem = f"census-acs5-2024-b01003-{query_key}"
        destination = output_dir / "shared"
        if (
            resume
            and (
                existing := _resume_named(
                    output_dir=destination,
                    stem=stem,
                    suffix=".json",
                    source_id=connector.source_id,
                )
            )
            is not None
        ):
            return existing
        last_error: ConnectorError | None = None
        async with semaphore:
            for attempt in range(attempts):
                try:
                    return await connector.fetch(population_query, destination)
                except ConnectorError as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    async def one(city_index: int, kind: str) -> FetchResult:
        spec = DEEP_CITY_SPECS[city_index]
        destination = output_dir / spec.city_id
        census_query = CensusPlaceQuery(
            state_fips=spec.census_state_fips,
            place_fips=spec.census_place_fips,
        )
        if kind == "boundary":
            boundary_connector = CensusTIGERPlaceConnector()
            source_id = boundary_connector.source_id
            stem = f"census-tigerweb-place-{census_query.geoid}"
            suffix = ".geojson"

            async def acquire() -> FetchResult:
                return await boundary_connector.fetch(census_query, destination)

        else:
            climate_query = NASAPowerDailyQuery(
                latitude=spec.center_latitude,
                longitude=spec.center_longitude,
                start=start,
                end=end_inclusive,
                parameters=("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "WS10M", "RH2M"),
            )
            climate_connector = NASAPowerDailyConnector()
            source_id = climate_connector.source_id
            query_key = sha256_bytes(canonical_json(climate_query.model_dump(mode="json")))[7:19]
            stem = f"nasa-power-{query_key}"
            suffix = ".geojson"

            async def acquire() -> FetchResult:
                return await climate_connector.fetch(climate_query, destination)

        acquire_one: Callable[[], Awaitable[FetchResult]] = acquire
        if (
            resume
            and (
                existing := _resume_named(
                    output_dir=destination,
                    stem=stem,
                    suffix=suffix,
                    source_id=source_id,
                )
            )
            is not None
        ):
            return existing
        last_error: ConnectorError | None = None
        async with semaphore:
            for attempt in range(attempts):
                try:
                    return await acquire_one()
                except ConnectorError as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    tasks = [population()] + [
        one(city_index, kind)
        for city_index in range(len(DEEP_CITY_SPECS))
        for kind in ("boundary", "climate")
    ]
    results = sorted(await asyncio.gather(*tasks), key=lambda item: item.artifact_path.as_posix())
    return TierDContextFetchReport(
        city_count=len(DEEP_CITY_SPECS),
        artifact_count=len(results),
        artifact_paths=[item.artifact_path for item in results],
        manifest_paths=[item.manifest_path for item in results],
        declared_source_units=sum(item.manifest.record_count for item in results),
    )


__all__ = [
    "TierDContextFetchReport",
    "TierDSourceFetchReport",
    "fetch_tier_d_context",
    "fetch_tier_d_sources",
]
