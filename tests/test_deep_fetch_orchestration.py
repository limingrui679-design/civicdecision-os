from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from civicdecision.connectors.base import FetchResult
from civicdecision.connectors.census_places import (
    CensusACSPopulationTableConnector,
    CensusTIGERPlaceConnector,
)
from civicdecision.connectors.municipal_service import (
    MunicipalAggregation,
    MunicipalServiceConnector,
    MunicipalServiceQuery,
)
from civicdecision.connectors.nasa_power import NASAPowerDailyConnector
from civicdecision.deep import fetch as deep_fetch
from civicdecision.deep.specs import DEEP_CITY_SPECS
from civicdecision.errors import ConnectorError
from civicdecision.protocols.source import SourceManifest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = ROOT / "examples/data/tier-d"


def _fake_result(output: Path, stem: str, source_id: str, count: int) -> FetchResult:
    artifact_path = output / f"{stem}.json"
    manifest_path = output / f"{stem}.manifest.json"
    return FetchResult(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest=SourceManifest(
            source_id=source_id,
            artifact_id=f"{source_id}.{stem}",
            name="Orchestration test artifact",
            publisher="Test publisher",
            landing_url="https://example.com/landing",
            data_url="https://example.com/data",
            license="Test fixture",
            retrieved_at=datetime(2026, 8, 13, tzinfo=UTC),
            query={"stem": stem},
            artifact_path=artifact_path.name,
            content_hash="sha256:" + "0" * 64,
            record_count=count,
            schema_fingerprint="sha256:" + "1" * 64,
            geographic_scope="test",
            temporal_scope="test",
            limitations=["No network call is made by this orchestration fixture."],
        ),
    )


@pytest.mark.asyncio
async def test_municipal_retry_recovers_without_changing_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connector = MunicipalServiceConnector(DEEP_CITY_SPECS[0].source)
    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )
    calls = 0

    async def flaky_fetch(query_seen: object, output_seen: Path) -> FetchResult:
        nonlocal calls
        calls += 1
        assert query_seen is query
        assert output_seen == tmp_path
        if calls == 1:
            raise ConnectorError("transient")
        return _fake_result(tmp_path, "recovered", connector.spec.source_id, 1)

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(connector, "fetch", flaky_fetch)
    monkeypatch.setattr(asyncio, "sleep", no_wait)
    result = await deep_fetch._fetch_with_retry(
        connector=connector,
        query=query,
        output_dir=tmp_path,
        attempts=2,
    )
    assert calls == 2
    assert result.manifest.record_count == 1


@pytest.mark.asyncio
async def test_municipal_retry_raises_last_connector_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connector = MunicipalServiceConnector(DEEP_CITY_SPECS[0].source)
    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 4, 3),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )

    async def unavailable(_: object, __: Path) -> FetchResult:
        raise ConnectorError("still unavailable")

    monkeypatch.setattr(connector, "fetch", unavailable)
    with pytest.raises(ConnectorError, match="still unavailable"):
        await deep_fetch._fetch_with_retry(
            connector=connector,
            query=query,
            output_dir=tmp_path,
            attempts=1,
        )


def test_resume_helpers_fail_closed_on_missing_or_wrong_identity(tmp_path: Path) -> None:
    query = MunicipalServiceQuery(
        start=date(2025, 4, 1),
        end=date(2025, 10, 1),
        aggregation=MunicipalAggregation.DAILY_CATEGORY,
    )
    connector = MunicipalServiceConnector(DEEP_CITY_SPECS[0].source)
    assert deep_fetch._resume_result(connector=connector, query=query, output_dir=tmp_path) is None
    assert (
        deep_fetch._resume_named(
            output_dir=tmp_path,
            stem="missing",
            suffix=".json",
            source_id="missing-source",
        )
        is None
    )

    city_directory = SOURCE_DIRECTORY / DEEP_CITY_SPECS[0].city_id
    assert (
        deep_fetch._resume_result(connector=connector, query=query, output_dir=city_directory)
        is not None
    )
    wrong_spec = connector.spec.model_copy(update={"source_id": "wrong-source"})
    wrong_connector = MunicipalServiceConnector(wrong_spec)
    assert (
        deep_fetch._resume_result(connector=wrong_connector, query=query, output_dir=city_directory)
        is None
    )

    climate_manifest = next(city_directory.glob("nasa-power-*.manifest.json"))
    stem = climate_manifest.name.removesuffix(".manifest.json")
    assert (
        deep_fetch._resume_named(
            output_dir=city_directory,
            stem=stem,
            suffix=".geojson",
            source_id="wrong-source",
        )
        is None
    )


@pytest.mark.asyncio
async def test_source_orchestrator_executes_all_32_nonresume_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: set[tuple[str, MunicipalAggregation]] = set()

    async def fake_fetch(
        self: MunicipalServiceConnector,
        query: MunicipalServiceQuery,
        output: Path,
        client: object | None = None,
    ) -> FetchResult:
        assert client is None
        key = (self.spec.city_id, query.aggregation)
        assert key not in seen
        seen.add(key)
        return _fake_result(
            output,
            f"{self.spec.city_id}.{query.aggregation.value}",
            self.spec.source_id,
            2,
        )

    monkeypatch.setattr(MunicipalServiceConnector, "fetch", fake_fetch)
    report = await deep_fetch.fetch_tier_d_sources(
        tmp_path,
        attempts=1,
        concurrency=8,
        resume=False,
    )
    assert len(seen) == 32
    assert report.city_count == 8
    assert report.aggregation_count == 32
    assert report.aggregate_rows == 64
    assert report.artifact_paths == sorted(report.artifact_paths)


@pytest.mark.asyncio
async def test_context_orchestrator_executes_shared_and_city_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = {"population": 0, "boundary": 0, "climate": 0}

    async def population_fetch(
        self: CensusACSPopulationTableConnector,
        query: object,
        output: Path,
        client: object | None = None,
    ) -> FetchResult:
        assert client is None
        seen["population"] += 1
        return _fake_result(output, "population", self.source_id, 8)

    async def boundary_fetch(
        self: CensusTIGERPlaceConnector,
        query: object,
        output: Path,
        client: object | None = None,
    ) -> FetchResult:
        assert client is None
        seen["boundary"] += 1
        return _fake_result(output, f"boundary-{seen['boundary']}", self.source_id, 1)

    async def climate_fetch(
        self: NASAPowerDailyConnector,
        query: object,
        output: Path,
        client: object | None = None,
    ) -> FetchResult:
        assert client is None
        seen["climate"] += 1
        return _fake_result(output, f"climate-{seen['climate']}", self.source_id, 1_098)

    monkeypatch.setattr(CensusACSPopulationTableConnector, "fetch", population_fetch)
    monkeypatch.setattr(CensusTIGERPlaceConnector, "fetch", boundary_fetch)
    monkeypatch.setattr(NASAPowerDailyConnector, "fetch", climate_fetch)
    report = await deep_fetch.fetch_tier_d_context(
        tmp_path,
        attempts=1,
        concurrency=8,
        resume=False,
    )
    assert seen == {"population": 1, "boundary": 8, "climate": 8}
    assert report.city_count == 8
    assert report.artifact_count == 17
    assert report.declared_source_units == 8_800
    assert report.artifact_paths == sorted(report.artifact_paths)
