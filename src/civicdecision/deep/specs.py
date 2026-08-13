"""Audited source and geography specifications for the eight Tier-D reference cities."""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field, TypeAdapter, model_validator

from civicdecision.connectors.municipal_service import (
    MunicipalDatasetSpec,
    MunicipalFieldMap,
    MunicipalPlatform,
)
from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel
from civicdecision.protocols.city import BoundingBox


def _url(value: str) -> AnyHttpUrl:
    return TypeAdapter(AnyHttpUrl).validate_python(value)


class DeepCitySpec(StrictModel):
    selection_order: int = Field(ge=1, le=8)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    timezone: str = Field(min_length=1)
    bbox: BoundingBox
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    census_state_fips: str = Field(pattern=r"^[0-9]{2}$")
    census_place_fips: str = Field(pattern=r"^[0-9]{5}$")
    source: MunicipalDatasetSpec
    selection_rationale: list[str] = Field(min_length=2)
    city_specific_limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def aligned(self) -> DeepCitySpec:
        if (
            self.city_id != self.source.city_id
            or self.display_name != self.source.city_name
            or self.country_code != self.source.country_code
        ):
            raise ValueError("deep-city identity must align with its source specification")
        if not (
            self.bbox.west <= self.center_longitude <= self.bbox.east
            and self.bbox.south <= self.center_latitude <= self.bbox.north
        ):
            raise ValueError("deep-city center must fall inside its declared bounding box")
        return self


COMMON_REQUEST_LIMITATIONS = [
    "A service request is a resident or staff report, not a verified incident, exposure, need, "
    "or completed service outcome.",
    "Reporting access, awareness, channel choice, duplicate handling, and agency workflow create "
    "selection and measurement differences across places and time.",
    "Aggregated public records omit street addresses and free text and cannot support individual-"
    "level inference.",
]


DEEP_CITY_SPECS = (
    DeepCitySpec(
        selection_order=1,
        city_id="us.ny.new-york-city",
        display_name="New York City",
        country_code="US",
        timezone="America/New_York",
        bbox=BoundingBox(west=-74.2591, south=40.4774, east=-73.7002, north=40.9176),
        center_latitude=40.7128,
        center_longitude=-74.0060,
        census_state_fips="36",
        census_place_fips="51000",
        source=MunicipalDatasetSpec(
            source_id="nyc-open-data-311-aggregate",
            city_id="us.ny.new-york-city",
            city_name="New York City",
            country_code="US",
            publisher="City of New York",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.cityofnewyork.us/resource/erm2-nwe9.json"),
            landing_url=_url(
                "https://data.cityofnewyork.us/Social-Services/"
                "311-Service-Requests-from-2020-to-Present/erm2-nwe9"
            ),
            dataset_identifier="erm2-nwe9",
            fields=MunicipalFieldMap(
                opened_at="created_date",
                category="complaint_type",
                area="borough",
                status="status",
            ),
            license_summary="NYC Open Data terms and dataset-specific conditions",
            request_semantics="One NYC 311 service-request record",
            primary_limitations=COMMON_REQUEST_LIMITATIONS,
        ),
        selection_rationale=[
            "Large multi-agency request system with borough geography and a stable Socrata API.",
            "Creates a high-volume stress case for aggregation, taxonomy, and workflow status.",
        ],
        city_specific_limitations=[
            "Borough aggregation is too coarse for neighborhood-level equity decisions.",
            "Complaint types and agency practices can change inside the selected period.",
        ],
    ),
    DeepCitySpec(
        selection_order=2,
        city_id="us.ma.boston",
        display_name="Boston",
        country_code="US",
        timezone="America/New_York",
        bbox=BoundingBox(west=-71.1912, south=42.2279, east=-70.9220, north=42.4008),
        center_latitude=42.3601,
        center_longitude=-71.0589,
        census_state_fips="25",
        census_place_fips="07000",
        source=MunicipalDatasetSpec(
            source_id="boston-open-data-311-2025-aggregate",
            city_id="us.ma.boston",
            city_name="Boston",
            country_code="US",
            publisher="City of Boston",
            platform=MunicipalPlatform.CKAN_DATASTORE,
            endpoint=_url("https://data.boston.gov/api/3/action/datastore_search_sql"),
            landing_url=_url("https://data.boston.gov/dataset/311-service-requests"),
            dataset_identifier="9d7c2214-4709-478a-a2e8-fb2020a5bb94",
            fields=MunicipalFieldMap(
                opened_at="open_dt",
                category="case_title",
                area="neighborhood",
                status="case_status",
            ),
            license_summary="Open Data Commons Public Domain Dedication and License (PDDL)",
            request_semantics="One legacy BOS:311 service-request record in the 2025 resource",
            primary_limitations=[
                *COMMON_REQUEST_LIMITATIONS,
                "Boston began a backend transition in October 2025; this reference window ends "
                "before that transition and must not be joined to the new schema silently.",
            ],
        ),
        selection_rationale=[
            "CKAN DataStore exercises a second query platform and municipal neighborhood fields.",
            "A documented backend transition provides a real schema-versioning stress case.",
        ],
        city_specific_limitations=[
            "Neighborhood labels are operational attributes, not guaranteed official boundaries.",
            "The legacy and new BOS:311 systems require an explicit future crosswalk.",
        ],
    ),
    DeepCitySpec(
        selection_order=3,
        city_id="us.il.chicago",
        display_name="Chicago",
        country_code="US",
        timezone="America/Chicago",
        bbox=BoundingBox(west=-87.9401, south=41.6445, east=-87.5237, north=42.0230),
        center_latitude=41.8781,
        center_longitude=-87.6298,
        census_state_fips="17",
        census_place_fips="14000",
        source=MunicipalDatasetSpec(
            source_id="chicago-open-data-311-aggregate",
            city_id="us.il.chicago",
            city_name="Chicago",
            country_code="US",
            publisher="City of Chicago",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.cityofchicago.org/resource/v6vf-nfxy.json"),
            landing_url=_url(
                "https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy"
            ),
            dataset_identifier="v6vf-nfxy",
            fields=MunicipalFieldMap(
                opened_at="created_date",
                category="sr_type",
                area="community_area",
                status="status",
            ),
            license_summary="City of Chicago data portal Terms of Use",
            request_semantics="One Chicago 311 service-request record",
            primary_limitations=[
                *COMMON_REQUEST_LIMITATIONS,
                "Information-only calls can carry the 311 center address and should not be "
                "interpreted as incident locations.",
                "Legacy records coexist with records from the system launched in December 2018.",
            ],
        ),
        selection_rationale=[
            "Community-area fields support a finer spatial demand profile than citywide totals.",
            "Legacy flags and information-only calls expose operational-semantic failure modes.",
        ],
        city_specific_limitations=[
            "Community-area codes require an external geometry crosswalk for mapping.",
            "Completed request status does not verify that the underlying issue was resolved.",
        ],
    ),
    DeepCitySpec(
        selection_order=4,
        city_id="us.ca.san-francisco",
        display_name="San Francisco",
        country_code="US",
        timezone="America/Los_Angeles",
        bbox=BoundingBox(west=-122.5149, south=37.7081, east=-122.3570, north=37.8324),
        center_latitude=37.7749,
        center_longitude=-122.4194,
        census_state_fips="06",
        census_place_fips="67000",
        source=MunicipalDatasetSpec(
            source_id="san-francisco-open-data-311-aggregate",
            city_id="us.ca.san-francisco",
            city_name="San Francisco",
            country_code="US",
            publisher="San Francisco 311",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.sfgov.org/resource/vw6y-z8j6.json"),
            landing_url=_url("https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6"),
            dataset_identifier="vw6y-z8j6",
            fields=MunicipalFieldMap(
                opened_at="requested_datetime",
                category="service_name",
                area="analysis_neighborhood",
                status="status_description",
            ),
            license_summary="Open Data Commons Public Domain Dedication and License (PDDL)",
            request_semantics="One SF311 case record",
            primary_limitations=COMMON_REQUEST_LIMITATIONS,
        ),
        selection_rationale=[
            "Long-running Open311-derived case data include analysis-neighborhood labels.",
            "Dense urban geography provides a contrasting service-request taxonomy and scale.",
        ],
        city_specific_limitations=[
            "Analysis neighborhoods are analytical groupings and can mask within-area variation.",
            "Historical records can be updated after closure and are not immutable event logs.",
        ],
    ),
    DeepCitySpec(
        selection_order=5,
        city_id="us.wa.seattle",
        display_name="Seattle",
        country_code="US",
        timezone="America/Los_Angeles",
        bbox=BoundingBox(west=-122.4597, south=47.4810, east=-122.2244, north=47.7342),
        center_latitude=47.6062,
        center_longitude=-122.3321,
        census_state_fips="53",
        census_place_fips="63000",
        source=MunicipalDatasetSpec(
            source_id="seattle-open-data-customer-service-aggregate",
            city_id="us.wa.seattle",
            city_name="Seattle",
            country_code="US",
            publisher="City of Seattle",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.seattle.gov/resource/5ngg-rpne.json"),
            landing_url=_url(
                "https://data.seattle.gov/City-Administration/Customer-Service-Requests/5ngg-rpne"
            ),
            dataset_identifier="5ngg-rpne",
            fields=MunicipalFieldMap(
                opened_at="createddate",
                category="webintakeservicerequests",
                area="community_reporting_area",
                status="servicerequeststatusname",
            ),
            license_summary="Public Domain as listed by the City of Seattle data portal",
            request_semantics="One selected public customer-service-request record",
            primary_limitations=[
                *COMMON_REQUEST_LIMITATIONS,
                "The dataset contains selected public request types and is not the complete set "
                "of requests received by every department.",
            ],
        ),
        selection_rationale=[
            "Community reporting areas and daily refresh support temporal-spatial diagnostics.",
            "Selective publication tests explicit coverage and representativeness warnings.",
        ],
        city_specific_limitations=[
            "Published request types are a selected subset, so citywide demand totals are invalid.",
            "Current status does not contain a complete service-resolution history.",
        ],
    ),
    DeepCitySpec(
        selection_order=6,
        city_id="us.tx.austin",
        display_name="Austin",
        country_code="US",
        timezone="America/Chicago",
        bbox=BoundingBox(west=-97.9384, south=30.0987, east=-97.5615, north=30.5169),
        center_latitude=30.2672,
        center_longitude=-97.7431,
        census_state_fips="48",
        census_place_fips="05000",
        source=MunicipalDatasetSpec(
            source_id="austin-open-data-311-aggregate",
            city_id="us.tx.austin",
            city_name="Austin",
            country_code="US",
            publisher="City of Austin",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.austintexas.gov/resource/xwdj-i9he.json"),
            landing_url=_url(
                "https://data.austintexas.gov/Utilities-and-City-Services/"
                "Austin-311-Public-Data/xwdj-i9he"
            ),
            dataset_identifier="xwdj-i9he",
            fields=MunicipalFieldMap(
                opened_at="sr_created_date",
                category="sr_type_desc",
                area="sr_location_zip_code",
                status="sr_status_desc",
            ),
            license_summary="City of Austin open data portal terms and dataset conditions",
            request_semantics="One Austin 311 service-request record",
            primary_limitations=COMMON_REQUEST_LIMITATIONS,
        ),
        selection_rationale=[
            "Rapid-growth context and department taxonomy complement older coastal systems.",
            "ZIP-code aggregation tests geography that crosses municipal and neighborhood "
            "concepts.",
        ],
        city_specific_limitations=[
            "ZIP codes are postal units and do not align exactly with city boundaries or need.",
            "Mass-entry requests can be entered after field work and distort creation-time demand.",
        ],
    ),
    DeepCitySpec(
        selection_order=7,
        city_id="us.ca.los-angeles",
        display_name="Los Angeles",
        country_code="US",
        timezone="America/Los_Angeles",
        bbox=BoundingBox(west=-118.6682, south=33.7037, east=-118.1553, north=34.3373),
        center_latitude=34.0522,
        center_longitude=-118.2437,
        census_state_fips="06",
        census_place_fips="44000",
        source=MunicipalDatasetSpec(
            source_id="los-angeles-open-data-my311-2025-aggregate",
            city_id="us.ca.los-angeles",
            city_name="Los Angeles",
            country_code="US",
            publisher="City of Los Angeles Information Technology Agency",
            platform=MunicipalPlatform.SOCRATA,
            endpoint=_url("https://data.lacity.org/resource/h73f-gn57.json"),
            landing_url=_url(
                "https://data.lacity.org/City-Infrastructure-Service-Requests/"
                "MyLA311-Service-Request-Data-2025/h73f-gn57"  # pragma: allowlist secret
            ),
            dataset_identifier="h73f-gn57",
            fields=MunicipalFieldMap(
                opened_at="createddate",
                category="requesttype",
                area="ncname",
                status="status",
            ),
            license_summary=(
                "No dataset-specific license is displayed; use is subject to City of Los "
                "Angeles open-data terms"
            ),
            request_semantics="One MyLA311 2025 service-request record",
            primary_limitations=COMMON_REQUEST_LIMITATIONS,
        ),
        selection_rationale=[
            "Neighborhood-council fields and a very large city footprint stress spatial summaries.",
            "Annual dataset versioning tests explicit source-resource selection.",
        ],
        city_specific_limitations=[
            "The annual resource can be revised and later system migrations require new mappings.",
            "Blank neighborhood-council values prevent complete within-city allocation analysis.",
        ],
    ),
    DeepCitySpec(
        selection_order=8,
        city_id="us.pa.philadelphia",
        display_name="Philadelphia",
        country_code="US",
        timezone="America/New_York",
        bbox=BoundingBox(west=-75.2803, south=39.8670, east=-74.9558, north=40.1379),
        center_latitude=39.9526,
        center_longitude=-75.1652,
        census_state_fips="42",
        census_place_fips="60000",
        source=MunicipalDatasetSpec(
            source_id="philadelphia-open-data-311-aggregate",
            city_id="us.pa.philadelphia",
            city_name="Philadelphia",
            country_code="US",
            publisher="City of Philadelphia",
            platform=MunicipalPlatform.CARTO_SQL,
            endpoint=_url("https://phl.carto.com/api/v2/sql"),
            landing_url=_url(
                "https://opendataphilly.org/datasets/311-service-and-information-requests/"
            ),
            dataset_identifier="public_cases_fc",
            fields=MunicipalFieldMap(
                opened_at="requested_datetime",
                category="service_name",
                area="zipcode",
                status="status",
            ),
            license_summary="OpenDataPhilly and City of Philadelphia open-data terms",
            request_semantics="One Philly311 service or information request",
            primary_limitations=COMMON_REQUEST_LIMITATIONS,
        ),
        selection_rationale=[
            "CARTO SQL exercises a third platform and a separately governed open-data catalog.",
            "Service and information requests expose taxonomy semantics distinct from incidents.",
        ],
        city_specific_limitations=[
            "ZIP-code areas are not neighborhoods and can cross policy-relevant boundaries.",
            "Information requests should not be interpreted as physical service demand.",
        ],
    ),
)


def deep_city_spec(city_id: str) -> DeepCitySpec:
    """Resolve one reference-city source specification."""

    try:
        return next(item for item in DEEP_CITY_SPECS if item.city_id == city_id)
    except StopIteration as exc:
        raise KeyError(f"unknown Tier-D city: {city_id}") from exc


__all__ = ["DEEP_CITY_SPECS", "DeepCitySpec", "deep_city_spec"]
