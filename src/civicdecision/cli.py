"""CivicDecision command line interface."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from civicdecision import __version__
from civicdecision.connectors.base import atomic_write
from civicdecision.connectors.cdc_places import CDCPlacesConnector, CDCPlacesQuery
from civicdecision.connectors.eurostat import (
    EurostatStatisticsConnector,
    EurostatStatisticsQuery,
)
from civicdecision.connectors.nasa_power import (
    NASAPowerDailyConnector,
    NASAPowerDailyQuery,
    PowerCommunity,
    PowerTimeStandard,
)
from civicdecision.connectors.nyc_311 import NYC311Connector, NYC311Query
from civicdecision.connectors.open_fema import (
    OpenFEMADisasterConnector,
    OpenFEMADisasterQuery,
)
from civicdecision.connectors.registry import CONNECTOR_REGISTRY, registry_json
from civicdecision.connectors.usgs_earthquakes import (
    USGSEarthquakeConnector,
    USGSEarthquakeQuery,
)
from civicdecision.connectors.world_bank import (
    WorldBankIndicatorConnector,
    WorldBankIndicatorQuery,
)
from civicdecision.demos.heat_access import (
    HeatAccessDemoConfig,
    build_heat_access_pack,
    write_decision_artifacts,
)
from civicdecision.errors import CivicDecisionError
from civicdecision.io import validate_document
from civicdecision.protocols.city import CityAdapterManifest
from civicdecision.protocols.decision import DecisionPack
from civicdecision.protocols.scenario import PolicyScenario
from civicdecision.protocols.schemas import build_schemas
from civicdecision.protocols.source import SourceManifest

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
schemas_app = typer.Typer(no_args_is_help=True)
protocol_app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
demo_app = typer.Typer(no_args_is_help=True)
app.add_typer(schemas_app, name="schemas")
app.add_typer(protocol_app, name="protocol")
app.add_typer(sources_app, name="sources")
app.add_typer(demo_app, name="demo")
console = Console()


class ProtocolKind(StrEnum):
    CITY_ADAPTER = "city-adapter"
    POLICY_SCENARIO = "policy-scenario"
    DECISION_PACK = "decision-pack"


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    """Parse common ISO 8601 CLI timestamps, including a trailing ``Z``."""

    normalized = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc


def _parse_filters(values: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("filters must use key=value")
        key, item = value.split("=", 1)
        if not key or not item or key in filters:
            raise ValueError("filters require unique non-empty key=value pairs")
        filters[key] = item
    return filters


@app.command()
def version() -> None:
    """Print the installed software version."""

    console.print(__version__)


@schemas_app.command("build")
def schemas_build(
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("schemas"),
) -> None:
    """Generate the three deterministic public JSON Schemas."""

    for path in build_schemas(output):
        console.print(f"created {path}")


@protocol_app.command("validate")
def protocol_validate(kind: ProtocolKind, path: Path) -> None:
    """Validate a City Adapter, Policy Scenario, or DecisionPack document."""

    document: CityAdapterManifest | PolicyScenario | DecisionPack
    try:
        if kind is ProtocolKind.CITY_ADAPTER:
            document = validate_document(path, CityAdapterManifest)
        elif kind is ProtocolKind.POLICY_SCENARIO:
            document = validate_document(path, PolicyScenario)
        else:
            document = validate_document(path, DecisionPack)
    except CivicDecisionError as exc:
        console.print(f"[red]invalid[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(f"[green]valid[/green] {kind.value}: {path}")
    if isinstance(document, DecisionPack):
        console.print(f"content hash: {document.content_hash()}")


def _print_fetch(source: str, artifact: Path, manifest: Path, count: int, digest: str) -> None:
    table = Table(title=f"Fetched {source}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("records", str(count))
    table.add_row("artifact", str(artifact))
    table.add_row("manifest", str(manifest))
    table.add_row("sha256", digest)
    console.print(table)


@sources_app.command("verify")
def verify_source(
    manifest: Annotated[Path, typer.Argument()],
    root: Annotated[Path | None, typer.Option("--root")] = None,
) -> None:
    """Verify a source manifest, artifact path, and SHA-256 digest."""

    try:
        source = validate_document(manifest, SourceManifest)
        source.verify_artifact(root or manifest.parent)
    except CivicDecisionError as exc:
        console.print(f"[red]source verification failed[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(
        f"[green]verified[/green] {source.artifact_id}: "
        f"{source.record_count} records, {source.content_hash}"
    )


@sources_app.command("catalog")
def source_catalog(
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """List or write the deterministic implemented-connector catalog."""

    if output is not None:
        payload = json.dumps(
            json.loads(registry_json()),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        atomic_write(output, payload + b"\n")
        console.print(f"created {output}")
        return
    table = Table(title=f"Implemented source connectors ({len(CONNECTOR_REGISTRY)})")
    table.add_column("Source ID")
    table.add_column("Family")
    table.add_column("Scope")
    table.add_column("Authentication")
    for descriptor in CONNECTOR_REGISTRY:
        table.add_row(
            descriptor.id,
            descriptor.family.value,
            descriptor.scope.value,
            descriptor.authentication,
        )
    console.print(table)


@sources_app.command("usgs-earthquakes")
def fetch_usgs(
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")],
    min_magnitude: Annotated[float, typer.Option("--min-magnitude")] = 4.5,
    limit: Annotated[int, typer.Option("--limit")] = 1000,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/usgs"),
) -> None:
    """Fetch a bounded, versioned USGS Earthquake Catalog artifact."""

    try:
        query = USGSEarthquakeQuery(
            start=_parse_iso_datetime(start, "start"),
            end=_parse_iso_datetime(end, "end"),
            min_magnitude=min_magnitude,
            limit=limit,
        )
        result = asyncio.run(USGSEarthquakeConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("cdc-places")
def fetch_cdc_places(
    state: Annotated[str | None, typer.Option("--state")] = None,
    county_fips: Annotated[str | None, typer.Option("--county-fips")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 1000,
    offset: Annotated[int, typer.Option("--offset")] = 0,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/cdc-places"),
) -> None:
    """Fetch a bounded CDC PLACES 2025 census-tract artifact."""

    try:
        query = CDCPlacesQuery(
            state_abbr=state,
            county_fips=county_fips,
            limit=limit,
            offset=offset,
        )
        result = asyncio.run(CDCPlacesConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("world-bank")
def fetch_world_bank(
    indicator: Annotated[str, typer.Option("--indicator")],
    start_year: Annotated[int, typer.Option("--start-year")],
    end_year: Annotated[int, typer.Option("--end-year")],
    country: Annotated[str, typer.Option("--country")] = "all",
    page: Annotated[int, typer.Option("--page")] = 1,
    per_page: Annotated[int, typer.Option("--per-page")] = 100,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/world-bank"),
) -> None:
    """Fetch one bounded World Bank V2 indicator page."""

    try:
        query = WorldBankIndicatorQuery(
            indicator=indicator,
            country=country,
            start_year=start_year,
            end_year=end_year,
            page=page,
            per_page=per_page,
        )
        result = asyncio.run(WorldBankIndicatorConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("nasa-power")
def fetch_nasa_power(
    latitude: Annotated[float, typer.Option("--latitude")],
    longitude: Annotated[float, typer.Option("--longitude")],
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")],
    parameters: Annotated[str, typer.Option("--parameters")] = "T2M",
    community: Annotated[str, typer.Option("--community")] = "RE",
    time_standard: Annotated[str, typer.Option("--time-standard")] = "UTC",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/nasa-power"),
) -> None:
    """Fetch bounded NASA POWER daily gridded data for one point."""

    try:
        query = NASAPowerDailyQuery(
            latitude=latitude,
            longitude=longitude,
            start=_parse_iso_date(start, "start"),
            end=_parse_iso_date(end, "end"),
            parameters=tuple(item.strip() for item in parameters.split(",") if item.strip()),
            community=PowerCommunity(community),
            time_standard=PowerTimeStandard(time_standard),
        )
        result = asyncio.run(NASAPowerDailyConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("openfema")
def fetch_openfema(
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")],
    state: Annotated[str | None, typer.Option("--state")] = None,
    incident_type: Annotated[str | None, typer.Option("--incident-type")] = None,
    top: Annotated[int, typer.Option("--top")] = 100,
    skip: Annotated[int, typer.Option("--skip")] = 0,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/openfema"),
) -> None:
    """Fetch one bounded OpenFEMA disaster-declaration page."""

    try:
        query = OpenFEMADisasterQuery(
            start=_parse_iso_datetime(start, "start"),
            end=_parse_iso_datetime(end, "end"),
            state=state,
            incident_type=incident_type,
            top=top,
            skip=skip,
        )
        result = asyncio.run(OpenFEMADisasterConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("eurostat")
def fetch_eurostat(
    dataset: Annotated[str, typer.Option("--dataset")],
    filters: Annotated[list[str] | None, typer.Option("--filter")] = None,
    language: Annotated[str, typer.Option("--language")] = "en",
    max_cells: Annotated[int, typer.Option("--max-cells")] = 1000,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/eurostat"),
) -> None:
    """Fetch a bounded Eurostat JSON-stat subset using repeated key=value filters."""

    try:
        query = EurostatStatisticsQuery(
            dataset=dataset,
            filters=_parse_filters(filters or []),
            language=language,
            max_cells=max_cells,
        )
        result = asyncio.run(EurostatStatisticsConnector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@sources_app.command("nyc-311")
def fetch_nyc_311(
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")],
    borough: Annotated[str | None, typer.Option("--borough")] = None,
    agency: Annotated[str | None, typer.Option("--agency")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 1000,
    offset: Annotated[int, typer.Option("--offset")] = 0,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("data/raw/nyc-311"),
) -> None:
    """Fetch a bounded NYC 311 public-service request page."""

    try:
        query = NYC311Query(
            start=_parse_iso_datetime(start, "start"),
            end=_parse_iso_datetime(end, "end"),
            borough=borough,
            agency=agency,
            limit=limit,
            offset=offset,
        )
        result = asyncio.run(NYC311Connector().fetch(query, output))
    except (CivicDecisionError, ValueError) as exc:
        console.print(f"[red]fetch failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _print_fetch(
        result.manifest.source_id,
        result.artifact_path,
        result.manifest_path,
        result.manifest.record_count,
        result.manifest.content_hash,
    )


@demo_app.command("heat-access")
def demo_heat_access(
    data: Annotated[Path, typer.Option("--data")],
    manifest: Annotated[Path, typer.Option("--manifest")],
    scenario: Annotated[Path, typer.Option("--scenario")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path(
        "examples/outputs/suffolk-heat-access"
    ),
) -> None:
    """Build a reproducible public-sample heat-access DecisionPack and brief."""

    try:
        run_config = (
            validate_document(config, HeatAccessDemoConfig)
            if config is not None
            else HeatAccessDemoConfig()
        )
        pack = build_heat_access_pack(
            data,
            manifest,
            scenario,
            run_config,
            config_reference=config,
        )
        artifacts = write_decision_artifacts(pack, output)
    except CivicDecisionError as exc:
        console.print(f"[red]demo failed safely[/red] {exc}")
        raise typer.Exit(code=2) from exc
    table = Table(title="Compiled heat-access reference workflow")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("status", pack.status.value)
    table.add_row("options", str(len(pack.options)))
    table.add_row("selected", pack.recommendation.selected_option_id or "none")
    table.add_row("DecisionPack", str(artifacts.pack_path))
    table.add_row("brief", str(artifacts.brief_path))
    table.add_row("content hash", artifacts.content_hash)
    console.print(table)


if __name__ == "__main__":
    app()
