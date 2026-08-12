"""Deterministically compile verified public sources into Tier-S city bundles."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from math import isfinite
from pathlib import Path
from statistics import fmean
from typing import Any, cast

from pydantic import ValidationError

from civicdecision.connectors.base import atomic_write
from civicdecision.connectors.nasa_power import NASAPowerDailyQuery
from civicdecision.connectors.world_bank import WorldBankIndicatorQuery
from civicdecision.errors import AnalysisError
from civicdecision.io import validate_document
from civicdecision.protocols.base import StrictModel, sha256_file
from civicdecision.protocols.city import BoundingBox, CityAdapterManifest, CityTier, CoverageWindow
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.city_catalog import GlobalCityCatalog, GlobalCityCatalogEntry
from civicdecision.standardized.models import (
    DataQualityReport,
    DecisionReadiness,
    GeographicAlignment,
    QualityCheck,
    QualityStatus,
    ScenarioScreenStatus,
    SourceBinding,
    StandardizedCityBundle,
    StandardMetric,
    StandardScenarioRun,
    TierSExclusionRecord,
    TierSRegistry,
    TierSRegistryEntry,
)

REQUIRED_CLIMATE_PARAMETERS = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "WS10M",
    "RH2M",
)
REQUIRED_COUNTRY_INDICATORS = (
    "SP.URB.TOTL.IN.ZS",
    "SP.POP.TOTL",
    "NY.GDP.PCAP.CD",
)
CLIMATE_UNITS = {
    "T2M": "degrees Celsius",
    "T2M_MAX": "degrees Celsius",
    "T2M_MIN": "degrees Celsius",
    "PRECTOTCORR": "millimeters per day",
    "WS10M": "meters per second",
    "RH2M": "percent",
}
INDICATOR_UNITS = {
    "SP.URB.TOTL.IN.ZS": "percent",
    "SP.POP.TOTL": "people",
    "NY.GDP.PCAP.CD": "current USD per person",
}


class TierSBuildArtifacts(StrictModel):
    registry_path: Path
    coverage_matrix_path: Path
    comparison_csv_path: Path
    comparison_markdown_path: Path
    checksum_path: Path
    bundle_paths: list[Path]
    run_paths: list[Path]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"cannot read validated Tier-S input: {path}") from exc


def _write_model(path: Path, model: StrictModel) -> None:
    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    atomic_write(path, payload + b"\n")


def _manifest_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.manifest.json"))


def _load_manifests(directory: Path) -> list[tuple[Path, SourceManifest]]:
    loaded: list[tuple[Path, SourceManifest]] = []
    for path in _manifest_paths(directory):
        manifest = validate_document(path, SourceManifest)
        manifest.verify_artifact(path.parent)
        loaded.append((path, manifest))
    return loaded


def _load_country_context(
    directory: Path,
) -> tuple[dict[str, tuple[SourceManifest, float]], dict[str, SourceManifest]]:
    values: dict[str, tuple[SourceManifest, float]] = {}
    manifests_by_indicator: dict[str, SourceManifest] = {}
    loaded = _load_manifests(directory)
    for path, manifest in loaded:
        try:
            query = WorldBankIndicatorQuery.model_validate(manifest.query)
        except ValidationError as exc:
            raise AnalysisError(f"invalid World Bank Tier-S query: {path}") from exc
        if query.indicator not in REQUIRED_COUNTRY_INDICATORS:
            raise AnalysisError(f"unexpected Tier-S country indicator: {query.indicator}")
        if query.country != "all" or query.start_year != 2023 or query.end_year != 2023:
            raise AnalysisError("Tier-S World Bank pages must be 2023 all-country pages")
        if query.indicator in manifests_by_indicator:
            raise AnalysisError(f"duplicate Tier-S indicator page: {query.indicator}")
        payload = _read_json(path.parent / manifest.artifact_path)
        if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
            raise AnalysisError("Tier-S World Bank artifact has an unexpected shape")
        for row in payload[1]:
            if not isinstance(row, dict):
                raise AnalysisError("Tier-S World Bank record must be an object")
            country = row.get("country")
            value = row.get("value")
            if isinstance(value, int | float) and not isfinite(float(value)):
                raise AnalysisError("Tier-S World Bank value must be finite")
            if (
                isinstance(country, dict)
                and isinstance(country.get("id"), str)
                and isinstance(value, int | float)
            ):
                values[f"{query.indicator}|{country['id']}"] = (manifest, float(value))
        manifests_by_indicator[query.indicator] = manifest
    if set(manifests_by_indicator) != set(REQUIRED_COUNTRY_INDICATORS):
        raise AnalysisError("Tier-S country context does not contain exactly three indicators")
    return values, manifests_by_indicator


def _load_climate_artifacts(
    directory: Path,
) -> list[tuple[Path, SourceManifest, NASAPowerDailyQuery, dict[str, Any]]]:
    loaded: list[tuple[Path, SourceManifest, NASAPowerDailyQuery, dict[str, Any]]] = []
    for path, manifest in _load_manifests(directory):
        try:
            query = NASAPowerDailyQuery.model_validate(manifest.query)
        except ValidationError as exc:
            raise AnalysisError(f"invalid NASA POWER Tier-S query: {path}") from exc
        if (
            query.start != date(2024, 1, 1)
            or query.end != date(2024, 12, 31)
            or tuple(query.parameters) != REQUIRED_CLIMATE_PARAMETERS
        ):
            raise AnalysisError("Tier-S NASA POWER query does not match the standard contract")
        payload = _read_json(path.parent / manifest.artifact_path)
        if not isinstance(payload, dict):
            raise AnalysisError("Tier-S NASA POWER artifact must be an object")
        loaded.append((path, manifest, query, payload))
    return loaded


def _match_climate(
    city: GlobalCityCatalogEntry,
    artifacts: list[tuple[Path, SourceManifest, NASAPowerDailyQuery, dict[str, Any]]],
) -> tuple[SourceManifest, NASAPowerDailyQuery, dict[str, Any]] | None:
    tolerance = 1e-9
    matches = [
        (manifest, query, payload)
        for _, manifest, query, payload in artifacts
        if abs(query.latitude - city.location.latitude) <= tolerance
        and abs(query.longitude - city.location.longitude) <= tolerance
    ]
    if len(matches) > 1:
        raise AnalysisError(f"multiple NASA POWER artifacts match {city.city_id}")
    return matches[0] if matches else None


def _metric(
    identifier: str,
    value: float,
    unit: str,
    source: SourceManifest,
    geographic_scope: str,
    temporal_scope: str,
    limitations: list[str],
) -> StandardMetric:
    return StandardMetric(
        id=identifier,
        value=round(value, 6),
        unit=unit,
        evidence_type=EvidenceType.ESTIMATED,
        geographic_scope=geographic_scope,
        temporal_scope=temporal_scope,
        source_refs=[source.artifact_id],
        method="Direct summary of the named source series; no causal or municipal inference.",
        limitations=limitations,
    )


def _daily_series(payload: dict[str, Any]) -> tuple[dict[str, dict[str, float]], float, int]:
    header = payload.get("header")
    properties = payload.get("properties")
    if not isinstance(header, dict) or not isinstance(properties, dict):
        raise AnalysisError("NASA POWER Tier-S payload lacks header or properties")
    parameter = properties.get("parameter")
    if not isinstance(parameter, dict):
        raise AnalysisError("NASA POWER Tier-S payload lacks parameter series")
    fill_value = header.get("fill_value")
    if not isinstance(fill_value, int | float):
        raise AnalysisError("NASA POWER Tier-S payload lacks numeric fill value")
    series: dict[str, dict[str, float]] = {}
    missing = 0
    for name in REQUIRED_CLIMATE_PARAMETERS:
        raw = parameter.get(name)
        if not isinstance(raw, dict):
            raise AnalysisError(f"NASA POWER Tier-S payload lacks {name}")
        typed: dict[str, float] = {}
        for day, value in raw.items():
            if not isinstance(day, str) or not isinstance(value, int | float):
                raise AnalysisError("NASA POWER Tier-S series contains an invalid value")
            numeric = float(value)
            if not isfinite(numeric):
                raise AnalysisError("NASA POWER Tier-S series contains a non-finite value")
            if numeric == float(fill_value):
                missing += 1
            typed[day] = numeric
        series[name] = typed
    return series, float(fill_value), missing


def _build_quality_report(
    city: GlobalCityCatalogEntry,
    manifest: SourceManifest,
    query: NASAPowerDailyQuery,
    payload: dict[str, Any],
    series: dict[str, dict[str, float]],
    missing: int,
) -> DataQualityReport:
    expected_days = 366
    expected_values = expected_days * len(REQUIRED_CLIMATE_PARAMETERS)
    actual_values = sum(len(item) for item in series.values())
    geometry = payload.get("geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    coordinate_error = None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        coordinate_error = max(
            abs(float(coordinates[0]) - city.location.longitude),
            abs(float(coordinates[1]) - city.location.latitude),
        )
    day_sets = [set(values) for values in series.values()]
    aligned_days = len(set.intersection(*day_sets)) if day_sets else 0
    expected_day_keys = {
        (date(2024, 1, 1) + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(expected_days)
    }
    complete_aligned_calendar = bool(day_sets) and all(
        keys == expected_day_keys for keys in day_sets
    )
    checks = [
        QualityCheck(
            id="parsed-value-count",
            status=QualityStatus.PASS if actual_values == expected_values else QualityStatus.FAIL,
            measured=actual_values,
            expected=expected_values,
            details="Six parameters must each contain all 366 dates in leap year 2024.",
        ),
        QualityCheck(
            id="source-manifest-record-count",
            status=(
                QualityStatus.PASS if manifest.record_count == actual_values else QualityStatus.FAIL
            ),
            measured=manifest.record_count,
            expected=actual_values,
            details="The source manifest count must equal the independently parsed value count.",
        ),
        QualityCheck(
            id="aligned-daily-keys",
            status=QualityStatus.PASS if complete_aligned_calendar else QualityStatus.FAIL,
            measured=aligned_days,
            expected=expected_days,
            details="All standardized climate parameters must share the same daily keys.",
        ),
        QualityCheck(
            id="fill-value-count",
            status=QualityStatus.PASS if missing == 0 else QualityStatus.FAIL,
            measured=missing,
            expected=0,
            details="Required Tier-S climate values cannot use the source fill marker.",
        ),
        QualityCheck(
            id="coordinate-rounding",
            status=(
                QualityStatus.PASS
                if coordinate_error is not None and coordinate_error <= 0.001
                else QualityStatus.FAIL
            ),
            measured=coordinate_error,
            expected="maximum coordinate difference <= 0.001 degrees",
            details="POWER response coordinates are rounded relative to the GeoNames source point.",
        ),
        QualityCheck(
            id="query-city-point",
            status=(
                QualityStatus.PASS
                if query.latitude == city.location.latitude
                and query.longitude == city.location.longitude
                else QualityStatus.FAIL
            ),
            measured=f"{query.latitude},{query.longitude}",
            expected=f"{city.location.latitude},{city.location.longitude}",
            details="The request point must exactly equal the catalog city point.",
        ),
    ]
    return DataQualityReport(
        overall_status=(
            QualityStatus.FAIL
            if any(item.status is QualityStatus.FAIL for item in checks)
            else QualityStatus.PASS
        ),
        completeness_rate=(actual_values - missing) / expected_values,
        missing_values=missing,
        checks=checks,
        limitations=[
            "Completeness validates the retrieved gridded series, not its within-city "
            "representativeness.",
            "Coordinate agreement does not turn a gazetteer point into a municipal boundary.",
        ],
    )


def _country_metric(
    city: GlobalCityCatalogEntry,
    indicator: str,
    value: float,
    manifest: SourceManifest,
) -> StandardMetric:
    safe_id = indicator.lower().replace(".", "-")
    return _metric(
        f"country-{safe_id}",
        value,
        INDICATOR_UNITS[indicator],
        manifest,
        f"country-context={city.country_code}",
        "2023",
        [
            "This national aggregate is context only and must not be interpreted as a city value.",
            "World Bank indicator definitions, revisions, and comparability limits apply.",
        ],
    )


def _climate_metrics(
    city: GlobalCityCatalogEntry,
    manifest: SourceManifest,
    series: dict[str, dict[str, float]],
) -> list[StandardMetric]:
    scope = f"gridded-point-near=({city.location.latitude},{city.location.longitude})"
    limits = [
        "NASA POWER is a gridded analysis-ready product, not a station observation.",
        "One point does not measure within-city microclimate or individual exposure.",
    ]
    metrics = [
        _metric(
            "climate-t2m-annual-mean",
            fmean(series["T2M"].values()),
            CLIMATE_UNITS["T2M"],
            manifest,
            scope,
            "2024 daily series summarized annually",
            limits,
        ),
        _metric(
            "climate-t2m-max-annual-maximum",
            max(series["T2M_MAX"].values()),
            CLIMATE_UNITS["T2M_MAX"],
            manifest,
            scope,
            "2024 maximum of daily maximum series",
            limits,
        ),
        _metric(
            "climate-t2m-min-annual-minimum",
            min(series["T2M_MIN"].values()),
            CLIMATE_UNITS["T2M_MIN"],
            manifest,
            scope,
            "2024 minimum of daily minimum series",
            limits,
        ),
        _metric(
            "climate-precipitation-annual-sum",
            sum(series["PRECTOTCORR"].values()),
            "millimeters",
            manifest,
            scope,
            "2024 sum of daily corrected precipitation",
            limits,
        ),
        _metric(
            "climate-wind-speed-annual-mean",
            fmean(series["WS10M"].values()),
            CLIMATE_UNITS["WS10M"],
            manifest,
            scope,
            "2024 daily series summarized annually",
            limits,
        ),
        _metric(
            "climate-relative-humidity-annual-mean",
            fmean(series["RH2M"].values()),
            CLIMATE_UNITS["RH2M"],
            manifest,
            scope,
            "2024 daily series summarized annually",
            limits,
        ),
        _metric(
            "climate-days-t2m-max-ge-35c",
            float(sum(value >= 35 for value in series["T2M_MAX"].values())),
            "days",
            manifest,
            scope,
            "2024 count using a declared 35 degrees Celsius screening threshold",
            [
                *limits,
                "The 35-degree threshold is a transparent screen, not a local warning standard.",
            ],
        ),
        _metric(
            "climate-days-precipitation-ge-20mm",
            float(sum(value >= 20 for value in series["PRECTOTCORR"].values())),
            "days",
            manifest,
            scope,
            "2024 count using a declared 20 millimeters per day screening threshold",
            [
                *limits,
                "The 20-millimeter threshold is a transparent screen, not a flood model.",
            ],
        ),
    ]
    return metrics


def _build_scenario_runs(
    city: GlobalCityCatalogEntry,
    created_at: datetime,
    metrics: list[StandardMetric],
    climate_source: SourceManifest,
    context_sources: Iterable[SourceManifest],
) -> list[StandardScenarioRun]:
    by_id = {item.id: item for item in metrics}
    context_refs = [item.artifact_id for item in context_sources]
    common_limits = [
        "This is a standardized descriptive screen, not a forecast, causal result, "
        "simulation, optimization, or recommendation.",
        "No municipal boundary, population exposure surface, asset inventory, service "
        "network, or local policy constraint is present.",
    ]
    heat_metrics = [
        by_id["climate-t2m-annual-mean"],
        by_id["climate-t2m-max-annual-maximum"],
        by_id["climate-days-t2m-max-ge-35c"],
        by_id["climate-relative-humidity-annual-mean"],
        by_id["country-sp-urb-totl-in-zs"],
    ]
    precipitation_metrics = [
        by_id["climate-precipitation-annual-sum"],
        by_id["climate-days-precipitation-ge-20mm"],
        by_id["climate-wind-speed-annual-mean"],
        by_id["country-sp-pop-totl"],
    ]
    missing_metrics = [
        by_id["climate-t2m-max-annual-maximum"],
        by_id["country-ny-gdp-pcap-cd"],
    ]
    return [
        StandardScenarioRun(
            run_id=f"{city.city_id}.screen.heat.2024",
            scenario_id=f"{city.city_id}.heat-screen.v1",
            template_id="standard.heat-screen.v1",
            city_id=city.city_id,
            created_at=created_at,
            title=f"{city.name} 2024 heat-context descriptive screen",
            question=(
                "What does the standardized point series show, and what evidence is still "
                "required before heat-access planning?"
            ),
            status=ScenarioScreenStatus.SCREENED,
            decision_readiness=DecisionReadiness.DESCRIPTIVE_ONLY,
            source_refs=[climate_source.artifact_id, *context_refs],
            metrics=heat_metrics,
            interpretation=(
                "The run reports source-typed climate summaries and national context without "
                "estimating people exposed or an intervention effect."
            ),
            proposed_follow_up=[
                "Acquire an official municipal boundary and sub-city heat or land-surface "
                "observations.",
                "Add population, vulnerability, facilities, capacities, opening hours, and "
                "travel networks.",
            ],
            required_next_evidence=[
                "Observed local exposure and outcome measures.",
                "Versioned facilities and access network with jurisdiction-specific constraints.",
            ],
            limitations=common_limits,
        ),
        StandardScenarioRun(
            run_id=f"{city.city_id}.screen.precipitation.2024",
            scenario_id=f"{city.city_id}.precipitation-screen.v1",
            template_id="standard.precipitation-screen.v1",
            city_id=city.city_id,
            created_at=created_at,
            title=f"{city.name} 2024 precipitation-context descriptive screen",
            question=(
                "What does the standardized point series show, and what evidence is still "
                "required before flood or disruption planning?"
            ),
            status=ScenarioScreenStatus.SCREENED,
            decision_readiness=DecisionReadiness.DESCRIPTIVE_ONLY,
            source_refs=[climate_source.artifact_id, *context_refs],
            metrics=precipitation_metrics,
            interpretation=(
                "The run summarizes gridded precipitation and wind context but does not model "
                "inundation, damages, or service disruption."
            ),
            proposed_follow_up=[
                "Acquire official drainage, elevation, land-cover, asset, and incident data.",
                "Calibrate a local hydrologic or disruption model before comparing interventions.",
            ],
            required_next_evidence=[
                "Locally validated rainfall and flood observations.",
                "Versioned assets, networks, capacities, costs, and jurisdictional constraints.",
            ],
            limitations=common_limits,
        ),
        StandardScenarioRun(
            run_id=f"{city.city_id}.screen.policy-readiness.2024",
            scenario_id=f"{city.city_id}.policy-readiness.v1",
            template_id="standard.policy-readiness.v1",
            city_id=city.city_id,
            created_at=created_at,
            title=f"{city.name} intervention-readiness evidence gate",
            question=(
                "Can the current Tier-S evidence support a city intervention choice or "
                "claimed outcome?"
            ),
            status=ScenarioScreenStatus.INSUFFICIENT_EVIDENCE,
            decision_readiness=DecisionReadiness.INSUFFICIENT_EVIDENCE,
            source_refs=[climate_source.artifact_id, *context_refs],
            metrics=missing_metrics,
            interpretation=(
                "No. Point climate and country context do not identify affected people, "
                "feasible actions, costs, constraints, counterfactual outcomes, or observed "
                "impact."
            ),
            proposed_follow_up=[
                "Build a separate Tier-D adapter from official local sources.",
                "Release failed or infeasible results rather than upgrading these descriptors.",
            ],
            required_next_evidence=[
                "Municipal geography and local administrative or sensor data.",
                "Scenario-specific actions, budgets, capacities, equity constraints, and "
                "outcome evidence.",
                "Historical replay, simulation validation, or identification diagnostics "
                "appropriate to the claim.",
            ],
            limitations=[
                *common_limits,
                "Country GDP per capita is not a city budget, cost, income, or fiscal-capacity "
                "measure.",
            ],
        ),
    ]


def _bbox(city: GlobalCityCatalogEntry, padding: float = 0.05) -> BoundingBox:
    return BoundingBox(
        west=max(-180, city.location.longitude - padding),
        south=max(-90, city.location.latitude - padding),
        east=min(180, city.location.longitude + padding),
        north=min(90, city.location.latitude + padding),
    )


def _source_binding(
    manifest: SourceManifest, alignment: GeographicAlignment, role: str
) -> SourceBinding:
    return SourceBinding(
        source_id=manifest.source_id,
        artifact_id=manifest.artifact_id,
        content_hash=manifest.content_hash,
        alignment=alignment,
        role=role,
        geographic_scope=manifest.geographic_scope,
        temporal_scope=manifest.temporal_scope,
        limitations=manifest.limitations,
    )


def build_tier_s_registry(
    global_catalog_path: Path,
    climate_directory: Path,
    country_context_directory: Path,
    target_count: int = 30,
) -> tuple[TierSRegistry, list[StandardizedCityBundle]]:
    """Compile the first eligible globally ranked cities into strict Tier-S bundles."""

    if target_count < 1:
        raise AnalysisError("Tier-S target_count must be positive")
    catalog = validate_document(global_catalog_path, GlobalCityCatalog)
    climate_artifacts = _load_climate_artifacts(climate_directory)
    context_values, context_manifests = _load_country_context(country_context_directory)
    geonames_manifest = catalog.source_manifest
    bundles: list[StandardizedCityBundle] = []
    exclusions: list[TierSExclusionRecord] = []
    for city in catalog.cities:
        climate_match = _match_climate(city, climate_artifacts)
        context = {
            indicator: context_values.get(f"{indicator}|{city.country_code}")
            for indicator in REQUIRED_COUNTRY_INDICATORS
        }
        if climate_match is None or any(value is None for value in context.values()):
            reasons = []
            if climate_match is None:
                reasons.append("No matching 2024 NASA POWER six-parameter artifact is committed.")
            reasons.extend(
                f"World Bank 2023 {indicator} is missing for {city.country_code}."
                for indicator, value in context.items()
                if value is None
            )
            exclusions.append(
                TierSExclusionRecord(
                    tier_g_rank=city.selection_rank,
                    city_id=city.city_id,
                    name=city.name,
                    country_code=city.country_code,
                    reasons=reasons,
                )
            )
            continue
        climate_manifest, climate_query, climate_payload = climate_match
        typed_context = cast(
            dict[str, tuple[SourceManifest, float]],
            {key: value for key, value in context.items() if value is not None},
        )
        series, _, missing = _daily_series(climate_payload)
        quality = _build_quality_report(
            city,
            climate_manifest,
            climate_query,
            climate_payload,
            series,
            missing,
        )
        if quality.overall_status is QualityStatus.FAIL:
            failed = [item.id for item in quality.checks if item.status is QualityStatus.FAIL]
            raise AnalysisError(
                f"Tier-S required quality gates failed for {city.city_id}: {failed}"
            )
        country_metrics = [
            _country_metric(
                city, indicator, typed_context[indicator][1], typed_context[indicator][0]
            )
            for indicator in REQUIRED_COUNTRY_INDICATORS
        ]
        metrics = [*_climate_metrics(city, climate_manifest, series), *country_metrics]
        context_sources = [context_manifests[item] for item in REQUIRED_COUNTRY_INDICATORS]
        source_manifests = [geonames_manifest, climate_manifest, *context_sources]
        source_ids = list(dict.fromkeys(item.source_id for item in source_manifests))
        created_at = max(item.retrieved_at for item in source_manifests).astimezone(UTC)
        adapter = CityAdapterManifest(
            city_id=city.city_id,
            display_name=city.name,
            country_code=city.country_code,
            tier=CityTier.STANDARDIZED,
            timezone=city.timezone,
            bbox=_bbox(city),
            coverage=CoverageWindow(
                start=datetime(2023, 1, 1, tzinfo=UTC),
                end=datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC),
            ),
            source_ids=source_ids,
            capabilities=[
                "city-identity",
                "daily-climate-description",
                "country-context-description",
                "evidence-readiness-screening",
            ],
            data_gaps=[
                "No official municipal polygon is included.",
                "No sub-city population, exposure, facility, network, asset, cost, budget, or "
                "policy-constraint data are included.",
                "No source in this bundle establishes causal effects or observed intervention "
                "outcomes.",
            ],
            limitations=[
                "Tier S is a standardized cross-city screening bundle, not a deep city adapter.",
                "The bounding box is a deterministic point buffer for indexing, not an official "
                "boundary.",
                "National World Bank indicators are context proxies and cannot be interpreted "
                "as city measures.",
            ],
        )
        bindings = [
            _source_binding(
                geonames_manifest,
                GeographicAlignment.IDENTITY_POINT,
                "City identity, country code, timezone, and source point.",
            ),
            _source_binding(
                climate_manifest,
                GeographicAlignment.GRIDDED_POINT,
                "Daily gridded climate series at the catalog point.",
            ),
            *[
                _source_binding(
                    context_manifests[indicator],
                    GeographicAlignment.COUNTRY_CONTEXT,
                    f"Country-level context only: {indicator}.",
                )
                for indicator in REQUIRED_COUNTRY_INDICATORS
            ],
        ]
        runs = _build_scenario_runs(city, created_at, metrics, climate_manifest, context_sources)
        bundle = StandardizedCityBundle(
            bundle_id=f"{city.city_id}.tier-s.2024",
            created_at=created_at,
            adapter=adapter,
            catalog_entry=city,
            source_manifests=source_manifests,
            source_bindings=bindings,
            quality_report=quality,
            metrics=metrics,
            scenario_runs=runs,
            limitations=[
                "This bundle supports reproducible descriptive comparison and evidence-gap "
                "screening only.",
                "It does not support a city intervention recommendation, forecast, causal claim, "
                "simulated impact, or optimized action.",
            ],
        )
        bundles.append(bundle)
        if len(bundles) == target_count:
            break
    if len(bundles) != target_count:
        raise AnalysisError(
            f"only {len(bundles)} cities satisfy the Tier-S source and quality contract; "
            f"target is {target_count}"
        )
    entries = [
        TierSRegistryEntry(
            selection_order=order,
            tier_g_rank=bundle.catalog_entry.selection_rank,
            city_id=bundle.adapter.city_id,
            name=bundle.adapter.display_name,
            country_code=bundle.adapter.country_code,
            bundle_ref=f"cities/{bundle.adapter.city_id}/bundle.json",
            bundle_hash=bundle.content_hash(),
            run_refs=[f"runs/{run.run_id}.json" for run in bundle.scenario_runs],
            run_hashes=[run.content_hash() for run in bundle.scenario_runs],
            scenario_statuses=[run.status for run in bundle.scenario_runs],
            quality_status=bundle.quality_report.overall_status,
        )
        for order, bundle in enumerate(bundles, start=1)
    ]
    registry = TierSRegistry(
        registry_id="tier-s-standardized-cities.2024.v1",
        created_at=max(item.created_at for item in bundles),
        target_count=target_count,
        selection_method=(
            "Scan Tier-G cities in catalog rank order; select the first cities with an exact "
            "2024 NASA POWER six-parameter point artifact, non-null 2023 values for all three "
            "declared World Bank country-context indicators, and passing required quality gates."
        ),
        reference_climate_year=2024,
        reference_context_year=2023,
        required_climate_parameters=list(REQUIRED_CLIMATE_PARAMETERS),
        required_country_indicators=list(REQUIRED_COUNTRY_INDICATORS),
        entries=entries,
        exclusions_before_target=exclusions,
        limitations=[
            "Eligibility reflects source completeness, not policy priority or representativeness.",
            "Tier-S city points and country proxies do not constitute deep local city data.",
            "Scenario records are descriptive screens and explicit evidence gates, not "
            "DecisionPacks.",
        ],
    )
    return registry, bundles


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "missing"
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _comparison_outputs(
    registry: TierSRegistry,
    bundles: list[StandardizedCityBundle],
) -> tuple[bytes, bytes]:
    metric_ids = [
        "climate-t2m-annual-mean",
        "climate-t2m-max-annual-maximum",
        "climate-t2m-min-annual-minimum",
        "climate-precipitation-annual-sum",
        "climate-days-t2m-max-ge-35c",
        "climate-days-precipitation-ge-20mm",
        "climate-wind-speed-annual-mean",
        "climate-relative-humidity-annual-mean",
        "country-sp-urb-totl-in-zs",
        "country-sp-pop-totl",
        "country-ny-gdp-pcap-cd",
    ]
    csv_buffer = StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(
        [
            "selection_order",
            "tier_g_rank",
            "city_id",
            "name",
            "country_code",
            *metric_ids,
            "screened_runs",
            "insufficient_evidence_runs",
            "recommendations_issued",
        ]
    )
    climate_rows: list[str] = []
    context_rows: list[str] = []
    bundle_by_id = {item.adapter.city_id: item for item in bundles}
    for entry in registry.entries:
        bundle = bundle_by_id[entry.city_id]
        metrics = {item.id: item for item in bundle.metrics}
        writer.writerow(
            [
                entry.selection_order,
                entry.tier_g_rank,
                entry.city_id,
                entry.name,
                entry.country_code,
                *[_format_metric(metrics[item].value) for item in metric_ids],
                sum(status is ScenarioScreenStatus.SCREENED for status in entry.scenario_statuses),
                sum(
                    status is ScenarioScreenStatus.INSUFFICIENT_EVIDENCE
                    for status in entry.scenario_statuses
                ),
                sum(run.recommendation_issued for run in bundle.scenario_runs),
            ]
        )
        climate_rows.append(
            "| "
            + " | ".join(
                [
                    str(entry.selection_order),
                    entry.name,
                    entry.country_code,
                    _format_metric(metrics["climate-t2m-annual-mean"].value),
                    _format_metric(metrics["climate-t2m-max-annual-maximum"].value),
                    _format_metric(metrics["climate-days-t2m-max-ge-35c"].value),
                    _format_metric(metrics["climate-precipitation-annual-sum"].value),
                    _format_metric(metrics["climate-days-precipitation-ge-20mm"].value),
                ]
            )
            + " |"
        )
        context_rows.append(
            "| "
            + " | ".join(
                [
                    str(entry.selection_order),
                    entry.name,
                    entry.country_code,
                    _format_metric(metrics["country-sp-urb-totl-in-zs"].value),
                    _format_metric(metrics["country-sp-pop-totl"].value),
                    _format_metric(metrics["country-ny-gdp-pcap-cd"].value),
                ]
            )
            + " |"
        )
    exclusion_lines = [
        f"- Tier-G rank {item.tier_g_rank}, {item.name} ({item.country_code}): "
        + "; ".join(item.reasons)
        for item in registry.exclusions_before_target
    ] or ["- None before the target was reached."]
    markdown = "\n".join(
        [
            "# Tier-S cross-city descriptive comparison",
            "",
            f"Registry: `{registry.registry_id}`",
            f"Registry content hash: `{registry.content_hash()}`",
            f"Cities: {len(registry.entries)}; independent scenario screening records: "
            f"{sum(len(item.run_refs) for item in registry.entries)}.",
            "",
            "This report compares the same source fields and years. It does not construct a "
            "composite score, policy ranking, forecast, causal estimate, simulated impact, or "
            "intervention recommendation. NASA POWER values are gridded point products. World "
            "Bank values are national context and are not city values.",
            "",
            "## 2024 gridded point climate summaries",
            "",
            "| Order | City | Code | Mean T2M C | Max daily T2M_MAX C | Days >=35 C | "
            "Precipitation sum mm | Days >=20 mm |",
            "|---:|---|:---:|---:|---:|---:|---:|---:|",
            *climate_rows,
            "",
            "## 2023 national context proxies",
            "",
            "| Order | City identity | Code | Urban population % | National population | "
            "GDP per capita current USD |",
            "|---:|---|:---:|---:|---:|---:|",
            *context_rows,
            "",
            "## Eligibility exclusions before target completion",
            "",
            *exclusion_lines,
            "",
            "## Evidence gate",
            "",
            "Each city has two `screened` descriptive records and one "
            "`insufficient-evidence` policy-readiness record. Every record sets "
            "`recommendation_issued=false`. Local boundaries, populations, exposure surfaces, "
            "facilities, networks, assets, costs, budgets, policy constraints, outcomes, and "
            "identification evidence remain required for Tier-D analysis.",
            "",
        ]
    )
    return csv_buffer.getvalue().encode("utf-8"), markdown.encode("utf-8")


def write_tier_s_artifacts(
    registry: TierSRegistry,
    bundles: list[StandardizedCityBundle],
    output_directory: Path,
) -> TierSBuildArtifacts:
    """Write registry, per-city bundles, independent scenario records, coverage, and checksums."""

    if len(bundles) != registry.target_count:
        raise AnalysisError("Tier-S bundle count does not match registry target")
    output_directory.mkdir(parents=True, exist_ok=True)
    registry_path = output_directory / "registry.json"
    coverage_path = output_directory / "coverage.csv"
    comparison_csv_path = output_directory / "cross-city-comparison.csv"
    comparison_markdown_path = output_directory / "cross-city-comparison.md"
    checksum_path = output_directory / "SHA256SUMS"
    _write_model(registry_path, registry)
    bundle_paths: list[Path] = []
    run_paths: list[Path] = []
    bundle_by_id = {item.adapter.city_id: item for item in bundles}
    for entry in registry.entries:
        bundle = bundle_by_id[entry.city_id]
        bundle_path = output_directory / entry.bundle_ref
        _write_model(bundle_path, bundle)
        bundle_paths.append(bundle_path)
        for ref, run in zip(entry.run_refs, bundle.scenario_runs, strict=True):
            run_path = output_directory / ref
            _write_model(run_path, run)
            run_paths.append(run_path)
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "selection_order",
            "tier_g_rank",
            "city_id",
            "name",
            "country_code",
            "quality_status",
            "scenario_runs",
            "screened_runs",
            "insufficient_evidence_runs",
            "bundle_hash",
        ]
    )
    for entry in registry.entries:
        writer.writerow(
            [
                entry.selection_order,
                entry.tier_g_rank,
                entry.city_id,
                entry.name,
                entry.country_code,
                entry.quality_status.value,
                len(entry.run_refs),
                sum(status is ScenarioScreenStatus.SCREENED for status in entry.scenario_statuses),
                sum(
                    status is ScenarioScreenStatus.INSUFFICIENT_EVIDENCE
                    for status in entry.scenario_statuses
                ),
                entry.bundle_hash,
            ]
        )
    atomic_write(coverage_path, buffer.getvalue().encode("utf-8"))
    comparison_csv, comparison_markdown = _comparison_outputs(registry, bundles)
    atomic_write(comparison_csv_path, comparison_csv)
    atomic_write(comparison_markdown_path, comparison_markdown)
    written = [
        registry_path,
        coverage_path,
        comparison_csv_path,
        comparison_markdown_path,
        *bundle_paths,
        *run_paths,
    ]
    checksum_lines = [
        f"{sha256_file(path)[7:]}  {path.relative_to(output_directory).as_posix()}"
        for path in written
    ]
    atomic_write(checksum_path, ("\n".join(checksum_lines) + "\n").encode("ascii"))
    TierSRegistry.model_validate_json(registry_path.read_bytes())
    for path in bundle_paths:
        StandardizedCityBundle.model_validate_json(path.read_bytes())
    for path in run_paths:
        StandardScenarioRun.model_validate_json(path.read_bytes())
    return TierSBuildArtifacts(
        registry_path=registry_path,
        coverage_matrix_path=coverage_path,
        comparison_csv_path=comparison_csv_path,
        comparison_markdown_path=comparison_markdown_path,
        checksum_path=checksum_path,
        bundle_paths=bundle_paths,
        run_paths=run_paths,
    )
