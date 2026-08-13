"""Load, reconcile, and summarize the committed Tier-D public evidence layer."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import fmean, median
from typing import Any, cast

from civicdecision.connectors.census_places import CensusPopulationArtifact, CensusPopulationRow
from civicdecision.connectors.municipal_service import (
    MunicipalAggregateArtifact,
    MunicipalAggregation,
)
from civicdecision.deep.models import (
    ApplicationSuite,
    CapabilityAssessment,
    CapabilityStatus,
    DeepMetric,
    DeepSourceBinding,
    SourceRole,
)
from civicdecision.deep.specs import DEEP_CITY_SPECS, DeepCitySpec
from civicdecision.errors import CivicDecisionError
from civicdecision.io import validate_document
from civicdecision.protocols.base import JsonValue
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.standardized.models import DataQualityReport, QualityCheck, QualityStatus


@dataclass(frozen=True)
class LoadedDeepCity:
    spec: DeepCitySpec
    municipal: dict[MunicipalAggregation, MunicipalAggregateArtifact]
    municipal_manifests: dict[MunicipalAggregation, SourceManifest]
    population: CensusPopulationArtifact
    population_row: CensusPopulationRow
    population_manifest: SourceManifest
    boundary: dict[str, Any]
    boundary_manifest: SourceManifest
    climate: dict[str, Any]
    climate_manifest: SourceManifest

    @property
    def source_manifests(self) -> list[SourceManifest]:
        return [
            *(self.municipal_manifests[item] for item in MunicipalAggregation),
            self.population_manifest,
            self.boundary_manifest,
            self.climate_manifest,
        ]

    @property
    def request_count(self) -> int:
        totals = {item.underlying_request_count for item in self.municipal.values()}
        if len(totals) != 1:
            raise CivicDecisionError(f"municipal totals do not reconcile for {self.spec.city_id}")
        return totals.pop()

    @property
    def start(self) -> date:
        values = {item.coverage_start for item in self.municipal.values()}
        if len(values) != 1:
            raise CivicDecisionError(f"municipal starts do not align for {self.spec.city_id}")
        return values.pop()

    @property
    def end_exclusive(self) -> date:
        values = {item.coverage_end_exclusive for item in self.municipal.values()}
        if len(values) != 1:
            raise CivicDecisionError(f"municipal ends do not align for {self.spec.city_id}")
        return values.pop()

    @property
    def reference_days(self) -> list[date]:
        return [
            self.start + timedelta(days=offset)
            for offset in range((self.end_exclusive - self.start).days)
        ]

    def daily_request_counts(self, keywords: list[str] | None = None) -> dict[date, int]:
        normalized = [item.casefold() for item in keywords or []]
        daily = {day: 0 for day in self.reference_days}
        artifact = self.municipal[MunicipalAggregation.DAILY_CATEGORY]
        for row in artifact.rows:
            assert row.service_date is not None and row.category is not None
            if normalized and not any(item in row.category.casefold() for item in normalized):
                continue
            daily[row.service_date] += row.request_count
        return daily

    def category_request_counts(self, keywords: list[str] | None = None) -> dict[str, int]:
        normalized = [item.casefold() for item in keywords or []]
        counts: Counter[str] = Counter()
        artifact = self.municipal[MunicipalAggregation.CATEGORY_STATUS]
        for row in artifact.rows:
            assert row.category is not None
            if normalized and not any(item in row.category.casefold() for item in normalized):
                continue
            counts[row.category] += row.request_count
        return dict(sorted(counts.items()))

    def climate_series(self, parameter: str) -> dict[str, float]:
        properties = self.climate.get("properties")
        if not isinstance(properties, dict):
            raise CivicDecisionError(f"NASA properties missing for {self.spec.city_id}")
        parameter_block = properties.get("parameter")
        if not isinstance(parameter_block, dict):
            raise CivicDecisionError(f"NASA parameter block missing for {self.spec.city_id}")
        series = parameter_block.get(parameter)
        if not isinstance(series, dict) or not all(
            isinstance(day, str) and isinstance(value, int | float) for day, value in series.items()
        ):
            raise CivicDecisionError(
                f"NASA parameter {parameter} is malformed for {self.spec.city_id}"
            )
        return {day: float(value) for day, value in sorted(series.items())}


def _single(paths: list[Path], description: str) -> Path:
    if len(paths) != 1:
        raise CivicDecisionError(f"expected one {description}, found {len(paths)}")
    return paths[0]


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CivicDecisionError(f"cannot load {description}: {path}") from exc
    if not isinstance(payload, dict):
        raise CivicDecisionError(f"{description} must be a JSON object: {path}")
    return payload


def load_tier_d_evidence(source_directory: Path) -> list[LoadedDeepCity]:
    """Load all 49 committed source artifacts and reject any structural drift."""

    shared = source_directory / "shared"
    population_manifest_path = _single(
        sorted(shared.glob("census-acs5-2024-b01003-*.manifest.json")),
        "shared ACS population manifest",
    )
    population_manifest = validate_document(population_manifest_path, SourceManifest)
    population_manifest.verify_artifact(shared)
    population = validate_document(
        shared / population_manifest.artifact_path, CensusPopulationArtifact
    )
    population_by_geoid = {item.geoid: item for item in population.rows}
    loaded: list[LoadedDeepCity] = []
    seen_manifest_paths = {population_manifest_path.resolve()}
    for spec in DEEP_CITY_SPECS:
        city_directory = source_directory / spec.city_id
        municipal: dict[MunicipalAggregation, MunicipalAggregateArtifact] = {}
        municipal_manifests: dict[MunicipalAggregation, SourceManifest] = {}
        for path in sorted(city_directory.glob(f"{spec.city_id}.*.manifest.json")):
            manifest = validate_document(path, SourceManifest)
            manifest.verify_artifact(city_directory)
            artifact = validate_document(
                city_directory / manifest.artifact_path, MunicipalAggregateArtifact
            )
            if (
                artifact.city_id != spec.city_id
                or artifact.source_id != spec.source.source_id
                or artifact.platform is not spec.source.platform
                or artifact.dataset_identifier != spec.source.dataset_identifier
                or manifest.source_id != spec.source.source_id
                or manifest.record_count != artifact.aggregate_row_count
            ):
                raise CivicDecisionError(f"municipal source identity drifted for {spec.city_id}")
            if artifact.aggregation in municipal:
                raise CivicDecisionError(
                    f"duplicate municipal aggregation for {spec.city_id}: {artifact.aggregation}"
                )
            municipal[artifact.aggregation] = artifact
            municipal_manifests[artifact.aggregation] = manifest
            seen_manifest_paths.add(path.resolve())
        if set(municipal) != set(MunicipalAggregation):
            raise CivicDecisionError(f"{spec.city_id} does not have all four municipal views")

        boundary_manifest_path = _single(
            sorted(city_directory.glob("census-tigerweb-place-*.manifest.json")),
            f"{spec.city_id} boundary manifest",
        )
        boundary_manifest = validate_document(boundary_manifest_path, SourceManifest)
        boundary_manifest.verify_artifact(city_directory)
        boundary = _load_json_object(
            city_directory / boundary_manifest.artifact_path, "TIGERweb boundary"
        )
        features = boundary.get("features")
        geoid = f"{spec.census_state_fips}{spec.census_place_fips}"
        if (
            not isinstance(features, list)
            or len(features) != 1
            or not isinstance(features[0], dict)
            or not isinstance(features[0].get("properties"), dict)
            or features[0]["properties"].get("GEOID") != geoid
        ):
            raise CivicDecisionError(f"TIGERweb GEOID drifted for {spec.city_id}")
        seen_manifest_paths.add(boundary_manifest_path.resolve())

        climate_manifest_path = _single(
            sorted(city_directory.glob("nasa-power-*.manifest.json")),
            f"{spec.city_id} climate manifest",
        )
        climate_manifest = validate_document(climate_manifest_path, SourceManifest)
        climate_manifest.verify_artifact(city_directory)
        climate = _load_json_object(
            city_directory / climate_manifest.artifact_path, "NASA POWER point series"
        )
        seen_manifest_paths.add(climate_manifest_path.resolve())
        if geoid not in population_by_geoid:
            raise CivicDecisionError(f"ACS population row is missing for {spec.city_id}")
        city = LoadedDeepCity(
            spec=spec,
            municipal=municipal,
            municipal_manifests=municipal_manifests,
            population=population,
            population_row=population_by_geoid[geoid],
            population_manifest=population_manifest,
            boundary=boundary,
            boundary_manifest=boundary_manifest,
            climate=climate,
            climate_manifest=climate_manifest,
        )
        _ = city.request_count, city.start, city.end_exclusive
        loaded.append(city)
    actual_manifests = set(source_directory.glob("**/*.manifest.json"))
    if {item.resolve() for item in actual_manifests} != seen_manifest_paths:
        extra = sorted(
            path.relative_to(source_directory).as_posix()
            for path in actual_manifests
            if path.resolve() not in seen_manifest_paths
        )
        raise CivicDecisionError(f"unrecognized Tier-D source manifests: {extra}")
    artifact_ids = {manifest.artifact_id for city in loaded for manifest in city.source_manifests}
    if len(artifact_ids) != 49:
        raise CivicDecisionError(
            f"Tier-D source layer must contain 49 deduplicated manifests, found {len(artifact_ids)}"
        )
    return loaded


def source_bindings(city: LoadedDeepCity) -> list[DeepSourceBinding]:
    """Bind each source to a role while preserving repeated-view semantics."""

    bindings: list[DeepSourceBinding] = []
    for aggregation in MunicipalAggregation:
        artifact = city.municipal[aggregation]
        manifest = city.municipal_manifests[aggregation]
        bindings.append(
            DeepSourceBinding(
                source_id=manifest.source_id,
                artifact_id=manifest.artifact_id,
                content_hash=manifest.content_hash,
                role=SourceRole.MUNICIPAL_DEMAND,
                evidence_type=EvidenceType.OBSERVED,
                geographic_scope=manifest.geographic_scope,
                temporal_scope=manifest.temporal_scope,
                record_semantics=(
                    f"One endpoint-side {aggregation.value} aggregate row over the same "
                    f"{artifact.underlying_request_count:,} underlying requests."
                ),
                underlying_observation_count=artifact.underlying_request_count,
                limitations=[
                    *manifest.limitations,
                    "The same requests appear in four independent aggregate views; their counts "
                    "must reconcile and must never be summed as distinct requests.",
                ],
            )
        )
    bindings.extend(
        [
            DeepSourceBinding(
                source_id=city.population_manifest.source_id,
                artifact_id=city.population_manifest.artifact_id,
                content_hash=city.population_manifest.content_hash,
                role=SourceRole.DEMOGRAPHIC_CONTEXT,
                evidence_type=EvidenceType.ESTIMATED,
                geographic_scope=(
                    f"ACS incorporated-place GEOID {city.population_row.geoid} selected from "
                    "the shared eight-place artifact"
                ),
                temporal_scope=city.population_manifest.temporal_scope,
                record_semantics="One place-level ACS five-year population estimate and 90% MOE.",
                underlying_observation_count=1,
                limitations=city.population_manifest.limitations,
            ),
            DeepSourceBinding(
                source_id=city.boundary_manifest.source_id,
                artifact_id=city.boundary_manifest.artifact_id,
                content_hash=city.boundary_manifest.content_hash,
                role=SourceRole.GEOGRAPHIC_IDENTITY,
                evidence_type=EvidenceType.OBSERVED,
                geographic_scope=city.boundary_manifest.geographic_scope,
                temporal_scope=city.boundary_manifest.temporal_scope,
                record_semantics="One current-service legal incorporated-place polygon.",
                underlying_observation_count=1,
                limitations=city.boundary_manifest.limitations,
            ),
            DeepSourceBinding(
                source_id=city.climate_manifest.source_id,
                artifact_id=city.climate_manifest.artifact_id,
                content_hash=city.climate_manifest.content_hash,
                role=SourceRole.CLIMATE_CONTEXT,
                evidence_type=EvidenceType.ESTIMATED,
                geographic_scope=city.climate_manifest.geographic_scope,
                temporal_scope=city.climate_manifest.temporal_scope,
                record_semantics="One gridded point-date-parameter value.",
                underlying_observation_count=city.climate_manifest.record_count,
                limitations=city.climate_manifest.limitations,
            ),
        ]
    )
    return bindings


def quality_report(city: LoadedDeepCity) -> DataQualityReport:
    """Reconcile independent views, dates, identities, and declared missingness."""

    expected_dates = {day.isoformat().replace("-", "") for day in city.reference_days}
    municipal_totals = {
        aggregation.value: artifact.underlying_request_count
        for aggregation, artifact in city.municipal.items()
    }
    municipal_rows_match = all(
        city.municipal_manifests[item].record_count == city.municipal[item].aggregate_row_count
        for item in MunicipalAggregation
    )
    observed_daily_dates = {
        row.service_date
        for row in city.municipal[MunicipalAggregation.DAILY_CATEGORY].rows
        if row.service_date is not None
    }
    area_status = city.municipal[MunicipalAggregation.AREA_STATUS]
    missing_area_requests = sum(
        row.request_count for row in area_status.rows if row.area == "(missing)"
    )
    climate_parameters = ("PRECTOTCORR", "RH2M", "T2M", "T2M_MAX", "T2M_MIN", "WS10M")
    climate_series = {item: city.climate_series(item) for item in climate_parameters}
    climate_dates_align = all(set(series) == expected_dates for series in climate_series.values())
    climate_values = [value for series in climate_series.values() for value in series.values()]
    climate_fill_free = all(value > -900 for value in climate_values)
    geoid = f"{city.spec.census_state_fips}{city.spec.census_place_fips}"
    boundary_feature = city.boundary["features"][0]
    checks = [
        QualityCheck(
            id="source-manifest-count",
            status=QualityStatus.PASS,
            measured=len(city.source_manifests),
            expected=7,
            details="Four municipal views plus population, boundary, and climate manifests loaded.",
        ),
        QualityCheck(
            id="municipal-view-total-reconciliation",
            status=(
                QualityStatus.PASS
                if len(set(municipal_totals.values())) == 1
                else QualityStatus.FAIL
            ),
            measured=cast(JsonValue, municipal_totals),
            expected="one identical underlying request total across four views",
            details="Independent category, area, date, and status aggregates must reconcile.",
        ),
        QualityCheck(
            id="municipal-manifest-row-reconciliation",
            status=QualityStatus.PASS if municipal_rows_match else QualityStatus.FAIL,
            measured=sum(item.aggregate_row_count for item in city.municipal.values()),
            expected=sum(item.record_count for item in city.municipal_manifests.values()),
            details="Every aggregate artifact row count must equal its source-manifest count.",
        ),
        QualityCheck(
            id="municipal-daily-activity-coverage",
            status=(
                QualityStatus.PASS
                if observed_daily_dates == set(city.reference_days)
                else QualityStatus.WARN
            ),
            measured=len(observed_daily_dates),
            expected=len(city.reference_days),
            details=(
                "Dates absent from the endpoint-side aggregate are zero-completed for regular "
                "forecasting, but the source cannot distinguish true zero activity from delayed "
                "or incomplete public-data publication."
            ),
        ),
        QualityCheck(
            id="municipal-positive-counts",
            status=(
                QualityStatus.PASS
                if all(
                    row.request_count > 0
                    for artifact in city.municipal.values()
                    for row in artifact.rows
                )
                else QualityStatus.FAIL
            ),
            measured="all-positive",
            expected="all-positive",
            details="Endpoint-side aggregate rows cannot contain zero or negative request counts.",
        ),
        QualityCheck(
            id="municipal-area-missingness",
            status=QualityStatus.WARN if missing_area_requests else QualityStatus.PASS,
            measured=missing_area_requests,
            expected=0,
            details=(
                "Missing operational area labels are retained and citywide use remains possible; "
                "area-level interpretation requires caution."
            ),
        ),
        QualityCheck(
            id="acs-place-identity",
            status=(
                QualityStatus.PASS if city.population_row.geoid == geoid else QualityStatus.FAIL
            ),
            measured=city.population_row.geoid,
            expected=geoid,
            details="The filtered ACS place row must match the declared incorporated-place GEOID.",
        ),
        QualityCheck(
            id="tigerweb-place-identity",
            status=(
                QualityStatus.PASS
                if boundary_feature["properties"].get("GEOID") == geoid
                else QualityStatus.FAIL
            ),
            measured=boundary_feature["properties"].get("GEOID"),
            expected=geoid,
            details="The legal boundary feature must match the declared incorporated-place GEOID.",
        ),
        QualityCheck(
            id="nasa-parameter-date-coverage",
            status=QualityStatus.PASS if climate_dates_align else QualityStatus.FAIL,
            measured={key: len(value) for key, value in climate_series.items()},
            expected={key: len(expected_dates) for key in climate_parameters},
            details="All six NASA POWER parameters must cover exactly the same 183 dates.",
        ),
        QualityCheck(
            id="nasa-fill-value-gate",
            status=QualityStatus.PASS if climate_fill_free else QualityStatus.FAIL,
            measured=sum(value <= -900 for value in climate_values),
            expected=0,
            details="NASA missing-value sentinels cannot enter city metrics or scenario inputs.",
        ),
    ]
    overall = (
        QualityStatus.FAIL
        if any(item.status is QualityStatus.FAIL for item in checks)
        else QualityStatus.WARN
        if any(item.status is QualityStatus.WARN for item in checks)
        else QualityStatus.PASS
    )
    return DataQualityReport(
        overall_status=overall,
        completeness_rate=(city.request_count - missing_area_requests) / city.request_count,
        missing_values=missing_area_requests,
        checks=checks,
        limitations=[
            "Completeness is defined only for the published operational-area field and does not "
            "measure unreported requests or omitted request types.",
            "A passing structural check establishes reproducibility, not substantive validity, "
            "causal identification, or fitness for a live decision.",
        ],
    )


def city_metrics(city: LoadedDeepCity) -> list[DeepMetric]:
    """Compute eighteen evidence-typed city metrics without inventing outcomes."""

    daily = list(city.daily_request_counts().values())
    category_counts = city.category_request_counts()
    area_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for row in city.municipal[MunicipalAggregation.AREA_STATUS].rows:
        assert row.area is not None and row.status is not None
        area_counts[row.area] += row.request_count
        status_counts[row.status] += row.request_count
    missing_area = area_counts.get("(missing)", 0)
    known_area_counts = {key: value for key, value in area_counts.items() if key != "(missing)"}
    daily_ref = city.municipal_manifests[MunicipalAggregation.DAILY_CATEGORY].artifact_id
    category_ref = city.municipal_manifests[MunicipalAggregation.CATEGORY_STATUS].artifact_id
    area_ref = city.municipal_manifests[MunicipalAggregation.AREA_STATUS].artifact_id
    population_ref = city.population_manifest.artifact_id
    climate_ref = city.climate_manifest.artifact_id
    population = city.population_row.estimate
    requests_per_100k = city.request_count / population * 100_000
    climate = {
        key: list(city.climate_series(key).values())
        for key in (
            "PRECTOTCORR",
            "RH2M",
            "T2M",
            "T2M_MAX",
            "WS10M",
        )
    }

    def metric(
        identifier: str,
        value: int | float | str,
        unit: str,
        evidence_type: EvidenceType,
        refs: list[str],
        method: str,
        interpretation: str,
        limitations: list[str],
    ) -> DeepMetric:
        return DeepMetric(
            id=identifier,
            value=value,
            unit=unit,
            evidence_type=evidence_type,
            source_refs=refs,
            method=method,
            interpretation=interpretation,
            limitations=limitations,
        )

    request_limit = [
        "Counts represent published service requests, not verified incidents, unmet need, or "
        "completed service outcomes."
    ]
    climate_limit = [
        "NASA POWER is a single gridded point and does not measure neighborhood exposure or a "
        "causal relationship with requests."
    ]
    return [
        metric(
            "municipal.requests-total",
            city.request_count,
            "requests",
            EvidenceType.OBSERVED,
            [category_ref],
            "Sum endpoint-side category-status aggregate counts over the reference window.",
            "Published requests received during the bounded 183-day window.",
            request_limit,
        ),
        metric(
            "municipal.daily-mean",
            fmean(daily),
            "requests/day",
            EvidenceType.OBSERVED,
            [daily_ref],
            "Arithmetic mean of 183 zero-complete daily aggregate totals.",
            "Average published daily request workload in the reference window.",
            request_limit,
        ),
        metric(
            "municipal.daily-median",
            float(median(daily)),
            "requests/day",
            EvidenceType.OBSERVED,
            [daily_ref],
            "Median of 183 zero-complete daily aggregate totals.",
            "Middle published daily workload, resistant to isolated high days.",
            request_limit,
        ),
        metric(
            "municipal.daily-maximum",
            max(daily),
            "requests/day",
            EvidenceType.OBSERVED,
            [daily_ref],
            "Maximum of 183 zero-complete daily aggregate totals.",
            "Largest published daily workload in the selected window.",
            request_limit,
        ),
        metric(
            "municipal.category-label-count",
            len([key for key in category_counts if key != "(missing)"]),
            "labels",
            EvidenceType.OBSERVED,
            [category_ref],
            "Count distinct non-missing public category strings.",
            "Operational taxonomy breadth, not a count of substantive problem types.",
            ["Label granularity and wording differ across cities and can change over time."],
        ),
        metric(
            "municipal.area-label-count",
            len(known_area_counts),
            "labels",
            EvidenceType.OBSERVED,
            [area_ref],
            "Count distinct non-missing operational area strings.",
            "Published spatial grouping breadth within the local request system.",
            ["Operational area labels are not necessarily official or comparable boundaries."],
        ),
        metric(
            "municipal.status-label-count",
            len(status_counts),
            "labels",
            EvidenceType.OBSERVED,
            [area_ref],
            "Count distinct public workflow status strings.",
            "Published workflow-state taxonomy breadth.",
            ["A closed status does not verify that the reported condition was resolved."],
        ),
        metric(
            "municipal.missing-area-share",
            missing_area / city.request_count,
            "share",
            EvidenceType.OBSERVED,
            [area_ref],
            "Requests with normalized '(missing)' area divided by reconciled request total.",
            "Share that cannot support an area-labeled analysis.",
            request_limit,
        ),
        metric(
            "municipal.top-category-share",
            max(category_counts.values()) / city.request_count,
            "share",
            EvidenceType.OBSERVED,
            [category_ref],
            "Largest category request count divided by the reconciled request total.",
            "Concentration in the single most frequent public category label.",
            request_limit,
        ),
        metric(
            "municipal.top-known-area-share",
            max(known_area_counts.values()) / city.request_count if known_area_counts else 0.0,
            "share",
            EvidenceType.OBSERVED,
            [area_ref],
            "Largest known-area request count divided by the reconciled city total.",
            "Operational request concentration in the most frequent known area label.",
            ["Area sizes, populations, reporting access, and published coverage are unadjusted."],
        ),
        metric(
            "demography.population-estimate",
            population,
            "people",
            EvidenceType.ESTIMATED,
            [population_ref],
            "ACS 2024 five-year B01003 incorporated-place estimate.",
            "Survey-based place population context, not a point-in-time administrative count.",
            city.population.limitations,
        ),
        metric(
            "demography.population-moe-90",
            city.population_row.margin_of_error_90,
            "people",
            EvidenceType.ESTIMATED,
            [population_ref],
            "Published ACS 90% margin, with controlled -555555555 encoded as effective zero.",
            "Sampling-uncertainty context for the place population estimate.",
            city.population.limitations,
        ),
        metric(
            "municipal.requests-per-100k-population",
            requests_per_100k,
            "requests/100,000 estimated residents/183 days",
            EvidenceType.ESTIMATED,
            [category_ref, population_ref],
            "Published request total divided by ACS five-year population estimate times 100,000.",
            "A rough denominator-adjusted reporting rate for this exact source window.",
            [
                "This combines different temporal constructs and does not measure need, incidence, "
                "service quality, or cross-city performance."
            ],
        ),
        metric(
            "climate.t2m-mean",
            fmean(climate["T2M"]),
            "degrees Celsius",
            EvidenceType.ESTIMATED,
            [climate_ref],
            "Arithmetic mean of 183 NASA POWER T2M daily point values.",
            "Reference-window gridded mean air-temperature context at the declared city point.",
            climate_limit,
        ),
        metric(
            "climate.t2m-max-maximum",
            max(climate["T2M_MAX"]),
            "degrees Celsius",
            EvidenceType.ESTIMATED,
            [climate_ref],
            "Maximum of 183 NASA POWER T2M_MAX daily point values.",
            "Highest gridded daily maximum-temperature context in the window.",
            climate_limit,
        ),
        metric(
            "climate.precipitation-total",
            sum(climate["PRECTOTCORR"]),
            "millimeters",
            EvidenceType.ESTIMATED,
            [climate_ref],
            "Sum of 183 NASA POWER PRECTOTCORR daily point values.",
            "Accumulated gridded precipitation context for the reference point and period.",
            climate_limit,
        ),
        metric(
            "climate.wind-speed-mean",
            fmean(climate["WS10M"]),
            "meters/second",
            EvidenceType.ESTIMATED,
            [climate_ref],
            "Arithmetic mean of 183 NASA POWER WS10M daily point values.",
            "Reference-window gridded ten-meter wind-speed context.",
            climate_limit,
        ),
        metric(
            "climate.relative-humidity-mean",
            fmean(climate["RH2M"]),
            "percent",
            EvidenceType.ESTIMATED,
            [climate_ref],
            "Arithmetic mean of 183 NASA POWER RH2M daily point values.",
            "Reference-window gridded two-meter relative-humidity context.",
            climate_limit,
        ),
    ]


def capability_assessments(city: LoadedDeepCity) -> list[CapabilityAssessment]:
    """Describe source readiness for every application suite without upgrading claims."""

    refs_by_role: dict[SourceRole, list[str]] = defaultdict(list)
    for binding in source_bindings(city):
        refs_by_role[binding.role].append(binding.artifact_id)

    def assessment(
        suite: ApplicationSuite,
        status: CapabilityStatus,
        required: list[SourceRole],
        diagnostics: list[str],
        limitations: list[str],
    ) -> CapabilityAssessment:
        satisfied = [role for role in required if refs_by_role.get(role)]
        return CapabilityAssessment(
            capability_id=f"suite.{suite.value}",
            status=status,
            required_source_roles=required,
            satisfied_source_roles=satisfied,
            evidence_refs=[reference for role in satisfied for reference in refs_by_role[role]],
            diagnostics=diagnostics,
            limitations=limitations,
        )

    generic = [
        "Source-role readiness does not establish calibrated action effects, implementation "
        "feasibility, external validity, or real-world impact."
    ]
    return [
        assessment(
            ApplicationSuite.PUBLIC_SERVICE,
            CapabilityStatus.READY,
            [SourceRole.MUNICIPAL_DEMAND],
            ["Four reconciled request aggregates support bounded workload planning."],
            generic,
        ),
        assessment(
            ApplicationSuite.CLIMATE_DISASTER,
            CapabilityStatus.LIMITED,
            [SourceRole.MUNICIPAL_DEMAND, SourceRole.CLIMATE_CONTEXT],
            ["Daily workload and one gridded climate point align over the reference period."],
            [
                *generic,
                "No hazard footprint, exposure surface, asset inventory, or impact outcome.",
            ],
        ),
        assessment(
            ApplicationSuite.POPULATION_HEALTH,
            CapabilityStatus.LIMITED,
            [
                SourceRole.MUNICIPAL_DEMAND,
                SourceRole.CLIMATE_CONTEXT,
                SourceRole.DEMOGRAPHIC_CONTEXT,
            ],
            ["Population and environmental context are present for guarded screening only."],
            [*generic, "No individual health outcome, exposure surface, or clinical denominator."],
        ),
        assessment(
            ApplicationSuite.HOUSING_LAND_USE,
            CapabilityStatus.LIMITED,
            [
                SourceRole.MUNICIPAL_DEMAND,
                SourceRole.DEMOGRAPHIC_CONTEXT,
                SourceRole.GEOGRAPHIC_IDENTITY,
            ],
            ["Request labels can be screened against a legal city identity and population total."],
            [*generic, "No parcel, permit, zoning, tenure, price, or verified condition records."],
        ),
        assessment(
            ApplicationSuite.INFRASTRUCTURE_FINANCE,
            CapabilityStatus.LIMITED,
            [SourceRole.MUNICIPAL_DEMAND, SourceRole.CLIMATE_CONTEXT],
            ["Maintenance-request proxies and climate context support hypothetical portfolios."],
            [*generic, "No asset registry, condition survey, lifecycle cost, or approved budget."],
        ),
        assessment(
            ApplicationSuite.BEHAVIORAL_EQUITY,
            CapabilityStatus.LIMITED,
            [SourceRole.MUNICIPAL_DEMAND, SourceRole.DEMOGRAPHIC_CONTEXT],
            ["Area-label distributions can be retained as operational diagnostics."],
            [*generic, "No subgroup outcomes, reporting-propensity model, or causal intervention."],
        ),
        assessment(
            ApplicationSuite.MOBILITY_ACCESS,
            CapabilityStatus.BLOCKED,
            [SourceRole.MUNICIPAL_DEMAND, SourceRole.NETWORK],
            ["Municipal demand is present, but no validated routable network is bound."],
            [*generic, "No GTFS, street topology, impedance model, or live disruption state."],
        ),
    ]


__all__ = [
    "LoadedDeepCity",
    "capability_assessments",
    "city_metrics",
    "load_tier_d_evidence",
    "quality_report",
    "source_bindings",
]
