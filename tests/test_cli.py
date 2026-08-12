from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from civicdecision.cli import app
from civicdecision.connectors.base import FetchResult
from civicdecision.connectors.cdc_places import CDCPlacesConnector
from civicdecision.connectors.geonames import GeoNamesCitiesConnector
from civicdecision.connectors.usgs_earthquakes import USGSEarthquakeConnector
from civicdecision.errors import ConnectorError
from civicdecision.protocols.source import SourceManifest

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_builds_schemas(tmp_path: Path) -> None:
    result = runner.invoke(app, ["schemas", "build", "--output", str(tmp_path)])
    assert result.exit_code == 0
    assert len(list(tmp_path.glob("*.schema.json"))) == 6


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("city-adapter", ROOT / "examples/cities/boston-cambridge.yaml"),
        ("policy-scenario", ROOT / "examples/scenarios/boston-heat-transit.yaml"),
    ],
)
def test_cli_validates_protocol(kind: str, path: Path) -> None:
    result = runner.invoke(app, ["protocol", "validate", kind, str(path)])
    assert result.exit_code == 0
    assert "valid" in result.output


def test_cli_rejects_invalid_protocol(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("city_id: INVALID ID\n", encoding="utf-8")
    result = runner.invoke(app, ["protocol", "validate", "city-adapter", str(invalid)])
    assert result.exit_code == 2
    assert "invalid" in result.output


def fake_fetch_result(tmp_path: Path, source_manifest: SourceManifest) -> FetchResult:
    return FetchResult(
        artifact_path=tmp_path / "artifact.json",
        manifest_path=tmp_path / "artifact.manifest.json",
        manifest=source_manifest,
    )


def test_cli_fetches_usgs_with_injected_connector(
    tmp_path: Path, source_manifest: SourceManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(self: USGSEarthquakeConnector, query: object, output: Path) -> FetchResult:
        return fake_fetch_result(tmp_path, source_manifest)

    monkeypatch.setattr(USGSEarthquakeConnector, "fetch", fake_fetch)
    result = runner.invoke(
        app,
        [
            "sources",
            "usgs-earthquakes",
            "--start",
            "2020-01-01T00:00:00Z",
            "--end",
            "2020-01-02T00:00:00Z",
            "--limit",
            "5",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "Fetched test-source" in result.output
    assert "records" in result.output


def test_cli_fetches_cdc_with_injected_connector(
    tmp_path: Path, source_manifest: SourceManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(self: CDCPlacesConnector, query: object, output: Path) -> FetchResult:
        return fake_fetch_result(tmp_path, source_manifest)

    monkeypatch.setattr(CDCPlacesConnector, "fetch", fake_fetch)
    result = runner.invoke(
        app,
        [
            "sources",
            "cdc-places",
            "--state",
            "MA",
            "--limit",
            "5",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "Fetched test-source" in result.output


def test_cli_fetches_geonames_with_injected_connector(
    tmp_path: Path, source_manifest: SourceManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(self: GeoNamesCitiesConnector, query: object, output: Path) -> FetchResult:
        return fake_fetch_result(tmp_path, source_manifest)

    monkeypatch.setattr(GeoNamesCitiesConnector, "fetch", fake_fetch)
    result = runner.invoke(
        app,
        ["sources", "geonames-cities", "--output", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Fetched test-source" in result.output


def test_cli_builds_global_city_artifacts(tmp_path: Path) -> None:
    manifest = ROOT / "examples/data/geonames/geonames-cities15000-98bc5fbd4deb.manifest.json"
    output = tmp_path / "cities"
    result = runner.invoke(
        app,
        [
            "cities",
            "build-global",
            "--manifest",
            str(manifest),
            "--target-count",
            "5",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert "Built global Tier-G city foundation" in result.output
    assert "coverage matrix" in result.output
    assert len(list(output.iterdir())) == 5


def test_cli_global_city_failure_is_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "cities",
            "build-global",
            "--manifest",
            str(tmp_path / "missing.manifest.json"),
            "--output",
            str(tmp_path / "cities"),
        ],
    )
    assert result.exit_code == 2
    assert "city catalog failed safely" in result.output


def test_cli_connector_failure_is_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_fetch(
        self: USGSEarthquakeConnector, query: object, output: Path
    ) -> FetchResult:
        raise ConnectorError("fixture outage")

    monkeypatch.setattr(USGSEarthquakeConnector, "fetch", failed_fetch)
    result = runner.invoke(
        app,
        [
            "sources",
            "usgs-earthquakes",
            "--start",
            "2020-01-01T00:00:00Z",
            "--end",
            "2020-01-02T00:00:00Z",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "failed safely" in result.output


def test_cli_rejects_invalid_cdc_query(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["sources", "cdc-places", "--state", "MASS", "--output", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "failed safely" in result.output


@pytest.mark.parametrize(
    ("start", "message"),
    [
        ("not-a-time", "ISO 8601"),
        ("2020-01-01T00:00:00", "timezone"),
    ],
)
def test_cli_rejects_ambiguous_usgs_timestamps(tmp_path: Path, start: str, message: str) -> None:
    result = runner.invoke(
        app,
        [
            "sources",
            "usgs-earthquakes",
            "--start",
            start,
            "--end",
            "2020-01-02T00:00:00Z",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert message in result.output


def test_cli_builds_and_validates_reference_decision_pack(tmp_path: Path) -> None:
    data_dir = ROOT / "examples/data/cdc-places"
    data = data_dir / "cdc-places-7ccf6e7d6dc3.json"
    manifest = data_dir / "cdc-places-7ccf6e7d6dc3.manifest.json"
    scenario = ROOT / "examples/scenarios/suffolk-heat-access-demo.yaml"
    result = runner.invoke(
        app,
        [
            "demo",
            "heat-access",
            "--data",
            str(data),
            "--manifest",
            str(manifest),
            "--scenario",
            str(scenario),
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "completed" in result.output
    pack = tmp_path / "decision-pack.json"
    validation = runner.invoke(app, ["protocol", "validate", "decision-pack", str(pack)])
    assert validation.exit_code == 0
    assert "content hash" in validation.output


def test_cli_verifies_source_artifact() -> None:
    manifest = ROOT / "examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json"
    result = runner.invoke(app, ["sources", "verify", str(manifest)])
    assert result.exit_code == 0
    assert "verified" in result.output


def test_cli_source_verification_fails_on_missing_artifact(tmp_path: Path) -> None:
    manifest = tmp_path / "missing.manifest.json"
    manifest.write_text("{}")
    result = runner.invoke(app, ["sources", "verify", str(manifest)])
    assert result.exit_code == 2
    assert "verification failed" in result.output


def test_cli_demo_failure_is_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "demo",
            "heat-access",
            "--data",
            str(tmp_path / "missing.json"),
            "--manifest",
            str(tmp_path / "missing.manifest.json"),
            "--scenario",
            str(ROOT / "examples/scenarios/suffolk-heat-access-demo.yaml"),
            "--output",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 2
    assert "demo failed safely" in result.output
