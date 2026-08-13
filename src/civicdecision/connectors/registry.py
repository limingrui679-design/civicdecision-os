"""Auditable registry for implemented and planned source connectors."""

from __future__ import annotations

import importlib
from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, Field, model_validator

from civicdecision.errors import ConnectorError
from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel, canonical_json


class ConnectorFamily(StrEnum):
    CLIMATE = "climate"
    DEMOGRAPHY = "demography"
    DISASTER = "disaster"
    GEOGRAPHY = "geography"
    HEALTH = "health"
    PUBLIC_SERVICE = "public-service"
    SEISMIC = "seismic"
    STATISTICS = "statistics"


class ConnectorScope(StrEnum):
    GLOBAL = "global"
    MULTINATIONAL = "multinational"
    NATIONAL = "national"
    LOCAL = "local"


class ConnectorDescriptor(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    family: ConnectorFamily
    scope: ConnectorScope
    publisher: str = Field(min_length=1)
    module: str = Field(pattern=r"^civicdecision\.connectors\.[a-z0-9_]+$")
    class_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9]+Connector$")
    documentation_url: AnyHttpUrl
    authentication: str = Field(min_length=1)
    paging_or_bound: str = Field(min_length=1)
    license_summary: str = Field(min_length=1)
    record_semantics: str = Field(min_length=1)
    primary_limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def module_can_be_loaded(self) -> ConnectorDescriptor:
        module = importlib.import_module(self.module)
        implementation: Any = getattr(module, self.class_name, None)
        if not isinstance(implementation, type):
            raise ValueError(f"connector class does not exist: {self.module}.{self.class_name}")
        if getattr(implementation, "source_id", None) != self.id:
            raise ValueError("registry id must match the connector source_id")
        return self


CONNECTOR_REGISTRY = (
    ConnectorDescriptor(
        id="census-acs5-2024-b01003-population",
        name="Census ACS 2024 five-year B01003 place population",
        family=ConnectorFamily.DEMOGRAPHY,
        scope=ConnectorScope.NATIONAL,
        publisher="U.S. Census Bureau",
        module="civicdecision.connectors.census_places",
        class_name="CensusACSPopulationTableConnector",
        documentation_url=AnyHttpUrl(
            "https://www.census.gov/data/developers/data-sets/acs-5year.html"
        ),
        authentication="No key for the official table-based summary-file download.",
        paging_or_bound="One <= 25 MiB B01003 file filtered to <= 50 named place GEOIDs",
        license_summary="U.S. Census Bureau public data; source attribution requested",
        record_semantics="One ACS five-year place population estimate with its 90% margin",
        primary_limitations=[
            "Survey estimates require margins of error and correct statistical universes."
        ],
    ),
    ConnectorDescriptor(
        id="census-tigerweb-current-incorporated-place",
        name="Census TIGERweb current incorporated-place boundary",
        family=ConnectorFamily.GEOGRAPHY,
        scope=ConnectorScope.NATIONAL,
        publisher="U.S. Census Bureau Geography Division",
        module="civicdecision.connectors.census_places",
        class_name="CensusTIGERPlaceConnector",
        documentation_url=AnyHttpUrl(
            "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_restmapservice.html"
        ),
        authentication="No API key.",
        paging_or_bound="Exactly one incorporated-place GEOID, polygon geometry, <= 10 MiB",
        license_summary="U.S. Census Bureau public geographic data",
        record_semantics="One current-service incorporated-place polygon feature",
        primary_limitations=[
            "Boundary vintages can change and do not define service or exposure geographies."
        ],
    ),
    ConnectorDescriptor(
        id="cdc-places-2025-tract",
        name="CDC PLACES 2025 census-tract estimates",
        family=ConnectorFamily.HEALTH,
        scope=ConnectorScope.NATIONAL,
        publisher="U.S. Centers for Disease Control and Prevention",
        module="civicdecision.connectors.cdc_places",
        class_name="CDCPlacesConnector",
        documentation_url=AnyHttpUrl(
            "https://data.cdc.gov/500-Cities-Places/"
            "PLACES-Census-Tract-Data-GIS-Friendly-"
            "Format-2025-/yjkw-uj5s"  # pragma: allowlist secret
        ),
        authentication="No key for bounded Socrata queries; app tokens may raise limits.",
        paging_or_bound="limit <= 50,000 plus explicit offset and optional state/county filter",
        license_summary="Public Domain with CDC attribution and methodology context",
        record_semantics="One model-based small-area estimate record per census tract",
        primary_limitations=["Area estimates are not individual outcomes or causal effects."],
    ),
    ConnectorDescriptor(
        id="eurostat-statistics-api",
        name="Eurostat Statistics API",
        family=ConnectorFamily.STATISTICS,
        scope=ConnectorScope.MULTINATIONAL,
        publisher="European Commission, Eurostat",
        module="civicdecision.connectors.eurostat",
        class_name="EurostatStatisticsConnector",
        documentation_url=AnyHttpUrl(
            "https://ec.europa.eu/eurostat/web/user-guides/data-browser/"
            "api-data-access/api-introduction"
        ),
        authentication="No key for Statistics API requests.",
        paging_or_bound="Required dimension filters plus local max_cells release gate",
        license_summary="Free reuse with attribution; dataset and third-party exceptions apply",
        record_semantics="Non-null JSON-stat observation cells with explicit dimensions",
        primary_limitations=["The API exposes latest data and does not version past snapshots."],
    ),
    ConnectorDescriptor(
        id="geonames-cities15000",
        name="GeoNames cities15000 gazetteer extract",
        family=ConnectorFamily.GEOGRAPHY,
        scope=ConnectorScope.GLOBAL,
        publisher="GeoNames",
        module="civicdecision.connectors.geonames",
        class_name="GeoNamesCitiesConnector",
        documentation_url=AnyHttpUrl("https://download.geonames.org/export/dump/"),
        authentication="No key for the downloadable gazetteer extract.",
        paging_or_bound="One fixed ZIP with compressed/uncompressed size and member-path gates",
        license_summary="Creative Commons Attribution 4.0; GeoNames attribution required",
        record_semantics="One populated-place gazetteer point per tab-delimited row",
        primary_limitations=["Points are not official city boundaries; source attributes vary."],
    ),
    ConnectorDescriptor(
        id="nasa-power-daily-point",
        name="NASA POWER daily point climate data",
        family=ConnectorFamily.CLIMATE,
        scope=ConnectorScope.GLOBAL,
        publisher="NASA Langley Research Center POWER Project",
        module="civicdecision.connectors.nasa_power",
        class_name="NASAPowerDailyConnector",
        documentation_url=AnyHttpUrl(
            "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"
        ),
        authentication="No key; requests must respect service and grid-rate guidance.",
        paging_or_bound="One point, <= 20 parameters, <= 367 days per reference request",
        license_summary="NASA public Earth science data with POWER citation guidance",
        record_semantics="One gridded parameter value for each point-date-parameter tuple",
        primary_limitations=["Gridded products are not station or street-level observations."],
    ),
    ConnectorDescriptor(
        id="nyc-open-data-311-2020-present",
        name="NYC 311 Service Requests",
        family=ConnectorFamily.PUBLIC_SERVICE,
        scope=ConnectorScope.LOCAL,
        publisher="City of New York",
        module="civicdecision.connectors.nyc_311",
        class_name="NYC311Connector",
        documentation_url=AnyHttpUrl(
            "https://data.cityofnewyork.us/Social-Services/"
            "311-Service-Requests-from-2020-to-Present/erm2-nwe9"
        ),
        authentication="No key for bounded Socrata queries; app tokens may raise limits.",
        paging_or_bound="Explicit half-open time window, limit <= 50,000, offset",
        license_summary="NYC Open Data terms and any dataset-specific conditions",
        record_semantics="One resident/service request record, not one verified incident",
        primary_limitations=["Reporting access and behavior create selection effects."],
    ),
    ConnectorDescriptor(
        id="openfema-disaster-declarations-v2",
        name="OpenFEMA Disaster Declarations Summaries V2",
        family=ConnectorFamily.DISASTER,
        scope=ConnectorScope.NATIONAL,
        publisher="U.S. Federal Emergency Management Agency",
        module="civicdecision.connectors.open_fema",
        class_name="OpenFEMADisasterConnector",
        documentation_url=AnyHttpUrl("https://www.fema.gov/about/openfema"),
        authentication="No registration or API key.",
        paging_or_bound="Explicit half-open time window, top <= 1,000, skip",
        license_summary="U.S. federal open data subject to FEMA.gov/OpenFEMA terms",
        record_semantics="One designated-area declaration record",
        primary_limitations=["A declaration does not measure loss, recovery, or policy effect."],
    ),
    ConnectorDescriptor(
        id="usgs-earthquakes",
        name="USGS Earthquake Catalog",
        family=ConnectorFamily.SEISMIC,
        scope=ConnectorScope.GLOBAL,
        publisher="U.S. Geological Survey",
        module="civicdecision.connectors.usgs_earthquakes",
        class_name="USGSEarthquakeConnector",
        documentation_url=AnyHttpUrl("https://earthquake.usgs.gov/fdsnws/event/1/"),
        authentication="No API key for bounded catalog queries.",
        paging_or_bound="Explicit time/magnitude window and limit <= 20,000",
        license_summary="U.S. government public data with source attribution guidance",
        record_semantics="One catalog earthquake feature",
        primary_limitations=["Catalog events can be revised and do not measure urban impact."],
    ),
    ConnectorDescriptor(
        id="world-bank-indicators-v2",
        name="World Bank Indicators V2",
        family=ConnectorFamily.DEMOGRAPHY,
        scope=ConnectorScope.GLOBAL,
        publisher="World Bank Group",
        module="civicdecision.connectors.world_bank",
        class_name="WorldBankIndicatorConnector",
        documentation_url=AnyHttpUrl(
            "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"
        ),
        authentication="No API key.",
        paging_or_bound="Indicator, country, year range, page, and per_page <= 1,000",
        license_summary="CC BY 4.0 default for Bank-produced open data; verify metadata",
        record_semantics="One country/aggregate-year indicator value",
        primary_limitations=["Indicator methods, revisions, and comparability vary."],
    ),
)


def registry_json() -> bytes:
    """Return the deterministic public connector catalog."""

    return canonical_json([item.model_dump(mode="json") for item in CONNECTOR_REGISTRY])


def connector_descriptor(source_id: str) -> ConnectorDescriptor:
    """Resolve a connector or fail with a typed error."""

    try:
        return next(item for item in CONNECTOR_REGISTRY if item.id == source_id)
    except StopIteration as exc:
        raise ConnectorError(f"unknown connector: {source_id}") from exc
