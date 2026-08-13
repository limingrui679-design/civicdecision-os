from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from civicdecision import __version__
from civicdecision.cli import app
from civicdecision.connectors.base import FetchResult
from civicdecision.connectors.cdc_places import CDCPlacesConnector
from civicdecision.connectors.eurostat import EurostatStatisticsConnector
from civicdecision.connectors.geonames import GeoNamesCitiesConnector
from civicdecision.connectors.nasa_power import NASAPowerDailyConnector
from civicdecision.connectors.nyc_311 import NYC311Connector
from civicdecision.connectors.open_fema import OpenFEMADisasterConnector
from civicdecision.connectors.usgs_earthquakes import USGSEarthquakeConnector
from civicdecision.connectors.world_bank import WorldBankIndicatorConnector
from civicdecision.errors import ConnectorError, IntegrityError
from civicdecision.product.store import ArtifactStore
from civicdecision.protocols.source import SourceManifest

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__ == version("civicdecision") == "0.8.0"


def test_cli_builds_schemas(tmp_path: Path) -> None:
    result = runner.invoke(app, ["schemas", "build", "--output", str(tmp_path)])
    assert result.exit_code == 0
    assert len(list(tmp_path.glob("*.schema.json"))) == 22


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


def test_cli_builds_standardized_city_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "standardized"
    result = runner.invoke(
        app,
        [
            "cities",
            "build-standardized",
            "--catalog",
            str(ROOT / "catalog/global-cities/cities-tier-g.json"),
            "--climate-directory",
            str(ROOT / "examples/data/tier-s/nasa-power"),
            "--country-context-directory",
            str(ROOT / "examples/data/tier-s/world-bank"),
            "--target-count",
            "2",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert "Built Tier-S standardized city foundation" in result.output
    assert "scenario runs" in result.output
    assert len(list((output / "cities").glob("*/bundle.json"))) == 2
    assert len(list((output / "runs").glob("*.json"))) == 6


def test_cli_standardized_city_failure_is_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "cities",
            "build-standardized",
            "--catalog",
            str(tmp_path / "missing.json"),
            "--climate-directory",
            str(tmp_path),
            "--country-context-directory",
            str(tmp_path),
            "--output",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 2
    assert "standardized city build failed safely" in result.output


def test_cli_builds_milestone_4_benchmarks(tmp_path: Path) -> None:
    output = tmp_path / "benchmarks"
    result = runner.invoke(
        app,
        [
            "benchmarks",
            "build-milestone-4",
            "--standardized-directory",
            str(ROOT / "catalog/standardized-cities"),
            "--nasa-source-directory",
            str(ROOT / "examples/data/tier-s/nasa-power"),
            "--replay-city-count",
            "1",
            "--optimization-task-count",
            "1",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert "Built milestone 4 analytical benchmarks" in result.output
    assert len(list((output / "historical-replays").glob("*.json"))) == 2
    assert len(list((output / "optimization-tasks").glob("*.json"))) == 1
    assert len(list((output / "engine-qualification").glob("*.json"))) == 5


def test_cli_benchmark_failure_is_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "benchmarks",
            "build-milestone-4",
            "--standardized-directory",
            str(tmp_path),
            "--nasa-source-directory",
            str(tmp_path),
            "--replay-city-count",
            "0",
            "--optimization-task-count",
            "1",
            "--output",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 2
    assert "benchmark build failed safely" in result.output


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


@pytest.fixture
def injected_product_store(
    product_store: ArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> ArtifactStore:
    monkeypatch.setattr(
        "civicdecision.cli._catalog_store",
        lambda root, verify_sources: product_store,
    )
    return product_store


def test_cli_product_summary_supports_table_and_json(
    injected_product_store: ArtifactStore,
) -> None:
    table = runner.invoke(app, ["catalog", "summary"])
    structured = runner.invoke(app, ["catalog", "summary", "--json"])
    assert table.exit_code == structured.exit_code == 0
    assert "258" in table.output and "catalog fingerprint" in table.output
    assert json.loads(structured.output)["tier_assignments"] == 288


def test_cli_product_city_browsing_and_detail(
    injected_product_store: ArtifactStore,
) -> None:
    listing = runner.invoke(
        app,
        ["catalog", "cities", "--tier", "D", "--limit", "2"],
    )
    detail = runner.invoke(app, ["catalog", "city", "us.tx.austin"])
    missing = runner.invoke(app, ["catalog", "city", "unknown.city"])
    assert listing.exit_code == detail.exit_code == 0
    assert "Austin" in listing.output and "Boston" in listing.output
    assert json.loads(detail.output)["city"]["tier"] == "D"
    assert missing.exit_code == 2 and "lookup failed" in missing.output


def test_cli_product_scenario_browsing_and_detail(
    injected_product_store: ArtifactStore,
) -> None:
    listing = runner.invoke(
        app,
        [
            "catalog",
            "scenarios",
            "--kind",
            "deep-pack",
            "--status",
            "insufficient-evidence",
            "--limit",
            "2",
            "--json",
        ],
    )
    detail = runner.invoke(app, ["catalog", "scenario", "tierd.us.tx.austin.11"])
    designs = runner.invoke(
        app,
        [
            "catalog",
            "designs",
            "--decision-type",
            "evaluate",
            "--limit",
            "1",
            "--json",
        ],
    )
    design = runner.invoke(
        app,
        ["catalog", "design", "scenario.climate.extreme-heat.heat-access-gaps.v1"],
    )
    families = runner.invoke(app, ["catalog", "design-families", "--limit", "1", "--json"])
    family = runner.invoke(app, ["catalog", "design-family", "climate.extreme-heat"])
    evidence = runner.invoke(app, ["catalog", "scenario-library-evidence"])
    assert all(
        result.exit_code == 0
        for result in (listing, detail, designs, design, families, family, evidence)
    )
    assert json.loads(listing.output)["pagination"]["total"] == 20
    assert json.loads(detail.output)["scenario"]["recommendation_issued"] is False
    assert json.loads(designs.output)["pagination"]["total"] == 30
    assert json.loads(design.output)["design"]["method_claimed"] is False
    assert json.loads(families.output)["pagination"]["total"] == 30
    assert len(json.loads(family.output)["designs"]) == 8
    assert json.loads(evidence.output)["design_only_scenarios"] == 228


def test_cli_product_sources_and_benchmarks(
    injected_product_store: ArtifactStore,
) -> None:
    sources = runner.invoke(
        app,
        ["catalog", "sources", "--query", "Austin", "--limit", "10"],
    )
    benchmark = runner.invoke(app, ["catalog", "benchmarks"])
    assert sources.exit_code == benchmark.exit_code == 0
    assert "City of Austin" in sources.output
    assert json.loads(benchmark.output)["run_artifacts"] == 145


def test_cli_exports_deterministic_openapi(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    result = runner.invoke(
        app,
        ["api", "export-openapi", "--root", str(ROOT), "--output", str(output)],
    )
    assert result.exit_code == 0
    assert output.read_bytes() == (ROOT / "catalog/product/openapi-v1.json").read_bytes()

    product_output = tmp_path / "product"
    product = runner.invoke(
        app,
        [
            "catalog",
            "build-product",
            "--root",
            str(ROOT),
            "--output",
            str(product_output),
        ],
    )
    assert product.exit_code == 0
    assert "338 product files" in product.output
    assert {
        path.relative_to(product_output): path.read_bytes()
        for path in product_output.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(ROOT / "catalog/product"): path.read_bytes()
        for path in (ROOT / "catalog/product").rglob("*")
        if path.is_file()
    }


def test_cli_scaffolds_and_validates_data_only_plugin(tmp_path: Path) -> None:
    output = tmp_path / "plugin"
    scaffold = runner.invoke(
        app,
        [
            "plugins",
            "scaffold",
            "--output",
            str(output),
            "--plugin-id",
            "review.adapter",
            "--name",
            "Review Adapter",
            "--author",
            "Reviewer",
        ],
    )
    validation = runner.invoke(
        app,
        [
            "plugins",
            "validate",
            str(output),
            "--expected-plugin-id",
            "review.adapter",
        ],
    )
    assert scaffold.exit_code == validation.exit_code == 0
    assert "code executed" in validation.output and "no" in validation.output


def test_cli_refuses_network_exposure_without_explicit_flag() -> None:
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "refusing network-exposed host" in result.output


def test_cli_connector_catalog_supports_table_and_deterministic_file(tmp_path: Path) -> None:
    table = runner.invoke(app, ["sources", "catalog"])
    output = tmp_path / "connectors.json"
    written = runner.invoke(app, ["sources", "catalog", "--output", str(output)])
    assert table.exit_code == written.exit_code == 0
    assert "Implemented source connectors" in table.output
    assert len(json.loads(output.read_text(encoding="utf-8"))) == 10


@pytest.mark.parametrize(
    ("connector_type", "arguments"),
    [
        (
            WorldBankIndicatorConnector,
            [
                "world-bank",
                "--indicator",
                "SP.POP.TOTL",
                "--start-year",
                "2020",
                "--end-year",
                "2021",
            ],
        ),
        (
            NASAPowerDailyConnector,
            [
                "nasa-power",
                "--latitude",
                "42.36",
                "--longitude",
                "-71.06",
                "--start",
                "2025-01-01",
                "--end",
                "2025-01-02",
                "--parameters",
                "T2M,PRECTOTCORR",
            ],
        ),
        (
            OpenFEMADisasterConnector,
            [
                "openfema",
                "--start",
                "2020-01-01T00:00:00Z",
                "--end",
                "2020-02-01T00:00:00Z",
                "--state",
                "MA",
            ],
        ),
        (
            EurostatStatisticsConnector,
            ["eurostat", "--dataset", "demo_r_pjanaggr3", "--filter", "geo=US"],
        ),
        (
            NYC311Connector,
            [
                "nyc-311",
                "--start",
                "2020-01-01T00:00:00Z",
                "--end",
                "2020-01-02T00:00:00Z",
                "--borough",
                "MANHATTAN",
            ],
        ),
    ],
)
def test_cli_fetches_each_extended_connector_with_typed_query(
    tmp_path: Path,
    source_manifest: SourceManifest,
    monkeypatch: pytest.MonkeyPatch,
    connector_type: type[Any],
    arguments: list[str],
) -> None:
    async def fake_fetch(self: object, query: object, output: Path) -> FetchResult:
        assert query is not None
        return fake_fetch_result(tmp_path, source_manifest)

    monkeypatch.setattr(connector_type, "fetch", fake_fetch)
    result = runner.invoke(
        app,
        ["sources", *arguments, "--output", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Fetched test-source" in result.output


def test_cli_rejects_unsafe_eurostat_filters(tmp_path: Path) -> None:
    cases = [
        ["--filter", "missing-separator"],
        ["--filter", "geo=US", "--filter", "geo=FR"],
        ["--filter", "=US"],
    ]
    for filters in cases:
        result = runner.invoke(
            app,
            [
                "sources",
                "eurostat",
                "--dataset",
                "fixture",
                *filters,
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 2
        assert "failed safely" in result.output


def test_cli_deep_fetch_commands_report_reconciled_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_sources(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(city_count=8, aggregation_count=32, aggregate_rows=148_836)

    async def fake_context(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(city_count=8, artifact_count=24, declared_source_units=8_800)

    monkeypatch.setattr("civicdecision.cli.fetch_tier_d_sources", fake_sources)
    monkeypatch.setattr("civicdecision.cli.fetch_tier_d_context", fake_context)
    sources = runner.invoke(app, ["deep", "fetch-sources", "--output", str(tmp_path)])
    context = runner.invoke(app, ["deep", "fetch-context", "--output", str(tmp_path)])
    assert sources.exit_code == context.exit_code == 0
    assert "148,836" in sources.output
    assert "8,800" in context.output


def test_cli_deep_fetch_rejects_invalid_date(tmp_path: Path) -> None:
    sources = runner.invoke(
        app,
        ["deep", "fetch-sources", "--start", "invalid", "--output", str(tmp_path)],
    )
    context = runner.invoke(
        app,
        ["deep", "fetch-context", "--end-inclusive", "invalid", "--output", str(tmp_path)],
    )
    assert sources.exit_code == context.exit_code == 2
    assert "YYYY-MM-DD" in sources.output and "YYYY-MM-DD" in context.output


def test_cli_deep_build_reports_committed_evidence_with_injected_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = SimpleNamespace(
        registry_path=ROOT / "catalog/deep-cities/registry.json",
        evidence_summary_path=ROOT / "catalog/deep-cities/evidence-summary.json",
        checksum_path=ROOT / "catalog/deep-cities/SHA256SUMS",
        artifact_paths=tuple(range(707)),
    )
    monkeypatch.setattr("civicdecision.cli.build_tier_d_artifacts", lambda *args: artifacts)
    result = runner.invoke(
        app,
        [
            "deep",
            "build",
            "--source-directory",
            str(tmp_path),
            "--output-directory",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 0
    assert "96" in result.output and "4,148,633" in result.output


def test_cli_deep_build_failure_is_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> None:
        raise IntegrityError("fixture integrity failure")

    monkeypatch.setattr("civicdecision.cli.build_tier_d_artifacts", fail)
    result = runner.invoke(
        app,
        [
            "deep",
            "build",
            "--source-directory",
            str(tmp_path),
            "--output-directory",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 2
    assert "failed safely" in result.output


def test_cli_product_collection_alternate_output_branches(
    injected_product_store: ArtifactStore,
) -> None:
    cities = runner.invoke(app, ["catalog", "cities", "--tier", "D", "--limit", "1", "--json"])
    scenarios = runner.invoke(
        app, ["catalog", "scenarios", "--kind", "reference-pack", "--limit", "1"]
    )
    sources = runner.invoke(app, ["catalog", "sources", "--query", "Austin", "--json"])
    missing = runner.invoke(app, ["catalog", "scenario", "unknown.scenario"])
    design_table = runner.invoke(
        app,
        ["catalog", "designs", "--implementation-status", "reference-implemented", "--limit", "2"],
    )
    family_table = runner.invoke(app, ["catalog", "design-families", "--limit", "2"])
    missing_design = runner.invoke(app, ["catalog", "design", "unknown.design"])
    missing_family = runner.invoke(app, ["catalog", "design-family", "unknown.family"])
    assert all(
        result.exit_code == 0 for result in (cities, scenarios, sources, design_table, family_table)
    )
    assert json.loads(cities.output)["pagination"]["total"] == 8
    assert "Scenario executions: 2" in scenarios.output
    assert json.loads(sources.output)["pagination"]["total"] == 5
    assert missing.exit_code == 2 and "lookup failed" in missing.output
    assert "Scenario designs: 12" in design_table.output
    assert "Scenario-design families: 30" in family_table.output
    assert missing_design.exit_code == missing_family.exit_code == 2


def test_cli_catalog_integrity_and_openapi_failures_are_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_store(*args: object, **kwargs: object) -> None:
        raise IntegrityError("fixture catalog failure")

    monkeypatch.setattr("civicdecision.cli.ArtifactStore", fail_store)
    catalog = runner.invoke(app, ["catalog", "summary"])
    openapi = runner.invoke(
        app,
        ["api", "export-openapi", "--root", str(tmp_path / "missing")],
    )
    product = runner.invoke(
        app,
        [
            "catalog",
            "build-product",
            "--root",
            str(tmp_path / "missing"),
            "--output",
            str(tmp_path / "product"),
        ],
    )
    assert catalog.exit_code == openapi.exit_code == product.exit_code == 2
    assert "catalog integrity failure" in catalog.output
    assert "OpenAPI export failed" in openapi.output
    assert "product artifact build failed safely" in product.output


def test_cli_plugin_failure_paths_are_nonzero(tmp_path: Path) -> None:
    output = tmp_path / "plugin"
    output.mkdir()
    scaffold = runner.invoke(
        app,
        [
            "plugins",
            "scaffold",
            "--output",
            str(output),
            "--plugin-id",
            "review.adapter",
            "--name",
            "Review",
            "--author",
            "Reviewer",
        ],
    )
    validation = runner.invoke(
        app,
        [
            "plugins",
            "validate",
            str(output),
            "--expected-plugin-id",
            "review.adapter",
        ],
    )
    assert scaffold.exit_code == validation.exit_code == 2
    assert "failed safely" in scaffold.output and "validation failed safely" in validation.output


def test_cli_serve_invokes_local_server_with_hardened_defaults(
    product_store: ArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr("civicdecision.api.create_app", lambda *args, **kwargs: application)

    def fake_run(app_value: object, **kwargs: object) -> None:
        captured.update(app=app_value, **kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", "--root", str(ROOT), "--port", "8765"])
    assert result.exit_code == 0
    assert captured == {
        "app": application,
        "host": "127.0.0.1",
        "port": 8765,
        "access_log": True,
        "server_header": False,
    }
