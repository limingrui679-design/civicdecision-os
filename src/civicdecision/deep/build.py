"""Build the eight-city Tier-D registry, 96 scenario packs, ledgers, and checksums."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, time
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from civicdecision.connectors.base import atomic_write
from civicdecision.connectors.municipal_service import MunicipalAggregation
from civicdecision.deep.compile import CompiledDeepScenario, compile_deep_scenario
from civicdecision.deep.load import (
    LoadedDeepCity,
    capability_assessments,
    city_metrics,
    load_tier_d_evidence,
    quality_report,
    source_bindings,
)
from civicdecision.deep.models import (
    DeepCityBundle,
    DeepScenarioPack,
    DeepScenarioStatus,
    TierDEvidenceSummary,
    TierDRegistry,
    TierDRegistryEntry,
    TierDScenarioEvidence,
    tier_d_canonical_json,
    tier_d_json_value,
)
from civicdecision.deep.templates import DEEP_SCENARIO_TEMPLATES
from civicdecision.errors import AnalysisError
from civicdecision.protocols.base import StrictModel, sha256_bytes, sha256_file
from civicdecision.protocols.city import CityAdapterManifest, CityTier, CoverageWindow
from civicdecision.protocols.source import SourceManifest
from civicdecision.standardized.models import QualityStatus


@dataclass(frozen=True)
class TierDCompilation:
    source_cities: list[LoadedDeepCity]
    compiled_scenarios: dict[str, list[CompiledDeepScenario]]
    bundles: list[DeepCityBundle]
    registry: TierDRegistry
    evidence_summary: TierDEvidenceSummary


class TierDBuildArtifacts(StrictModel):
    registry_path: Path
    evidence_summary_path: Path
    coverage_path: Path
    scenario_ledger_path: Path
    source_ledger_path: Path
    metric_ledger_path: Path
    summary_path: Path
    template_catalog_path: Path
    selection_method_path: Path
    anti_inflation_path: Path
    checksum_path: Path
    bundle_paths: list[Path]
    scenario_pack_paths: list[Path]
    artifact_paths: list[Path]


def _model_bytes(model: StrictModel) -> bytes:
    return tier_d_canonical_json(model) + b"\n"


def _adapter(city: LoadedDeepCity) -> CityAdapterManifest:
    return CityAdapterManifest(
        city_id=city.spec.city_id,
        display_name=city.spec.display_name,
        country_code=city.spec.country_code,
        tier=CityTier.DEEP,
        timezone=city.spec.timezone,
        bbox=city.spec.bbox,
        coverage=CoverageWindow(
            start=datetime.combine(city.start, time.min, tzinfo=ZoneInfo(city.spec.timezone)),
            end=datetime.combine(city.end_exclusive, time.min, tzinfo=ZoneInfo(city.spec.timezone)),
        ),
        source_ids=list(dict.fromkeys(item.source_id for item in city.source_manifests)),
        capabilities=[
            "official-local-demand-aggregation",
            "legal-boundary-binding",
            "population-context",
            "daily-climate-context",
            "transparent-baseline-forecasting",
            "seeded-workload-simulation",
            "bounded-portfolio-optimization",
            "paired-option-uncertainty",
            "negative-evidence-release",
            "decision-pack-compilation",
        ],
        data_gaps=[
            "No validated action-effect, operational cost, approved budget, staffing capacity, "
            "procurement, or implementation-outcome evidence is bound.",
            "No routable street, pedestrian, transit, utility, or multimodal network is bound.",
            "No parcel, asset-condition, facility, permit, subgroup-outcome, individual health, "
            "or causal intervention panel is bound.",
        ],
        limitations=[
            "Tier D means deeper reproducible local evidence and analytical orchestration; it "
            "does not mean production readiness, adoption, deployment, or policy validity.",
            "Municipal requests are reports and workflow records, not verified incidents, unique "
            "people, unmet need, or completed outcomes.",
            "Every simulated and optimized action coefficient remains hypothetical.",
        ],
    )


def _scenario_evidence(compiled: CompiledDeepScenario) -> TierDScenarioEvidence:
    pack = compiled.pack
    artifact_hashes: dict[str, str] = {
        item.kind: item.content_hash for item in pack.analytical_artifacts
    }
    artifact_hashes["deep-scenario-pack"] = sha256_bytes(_model_bytes(pack))
    return TierDScenarioEvidence(
        pack_id=pack.pack_id,
        city_id=pack.city_id,
        scenario_template_id=pack.scenario_template_id,
        suite=pack.suite,
        status=pack.status,
        observed_request_count=pack.observed_request_count,
        artifact_hashes=dict(sorted(artifact_hashes.items())),
        pack_file_hash=sha256_bytes(_model_bytes(pack)),
        forecast_input_observations=pack.forecast.observation_count if pack.forecast else 0,
        simulation_iterations=pack.simulation.config.iterations if pack.simulation else 0,
        optimization_search_space=(
            pack.optimization.solver.search_space_size if pack.optimization else 0
        ),
        optimization_evaluated_plans=(
            pack.optimization.solver.evaluated_plans if pack.optimization else 0
        ),
        optimization_feasible_plans=(
            pack.optimization.solver.feasible_plans if pack.optimization else 0
        ),
        uncertainty_option_draw_values=(
            sum(item.draws for item in pack.uncertainty.option_summaries) if pack.uncertainty else 0
        ),
    )


def compile_tier_d_reference(source_directory: Path) -> TierDCompilation:
    """Compile deterministic Tier-D models in memory from the 49 verified source artifacts."""

    cities = load_tier_d_evidence(source_directory)
    created_at = max(
        manifest.retrieved_at for city in cities for manifest in city.source_manifests
    ).astimezone(UTC)
    compiled_by_city: dict[str, list[CompiledDeepScenario]] = {}
    bundles: list[DeepCityBundle] = []
    entries: list[TierDRegistryEntry] = []
    evidence_rows: list[TierDScenarioEvidence] = []
    for city in cities:
        quality = quality_report(city)
        if quality.overall_status is QualityStatus.FAIL:
            failed = [item.id for item in quality.checks if item.status is QualityStatus.FAIL]
            raise AnalysisError(f"Tier-D quality gates failed for {city.spec.city_id}: {failed}")
        compiled = [
            compile_deep_scenario(city, template, created_at=created_at)
            for template in DEEP_SCENARIO_TEMPLATES
        ]
        compiled_by_city[city.spec.city_id] = compiled
        packs = [item.pack for item in compiled]
        bundle = DeepCityBundle(
            bundle_id=f"tierd.{city.spec.city_id}.bundle.v1",
            created_at=created_at,
            reference_period_start=city.start,
            reference_period_end_exclusive=city.end_exclusive,
            adapter=_adapter(city),
            source_manifests=city.source_manifests,
            source_bindings=source_bindings(city),
            quality_report=quality,
            metrics=city_metrics(city),
            capabilities=capability_assessments(city),
            scenario_packs=packs,
            selection_rationale=city.spec.selection_rationale,
            data_gaps=[
                "No local validated action-effect, implementation-cost, capacity, or outcome "
                "evidence is included.",
                "No routable mobility, utility, facility, parcel, or asset network is included.",
                "No intervention assignment or defensible causal comparison panel is included.",
            ],
            limitations=[
                *city.spec.city_specific_limitations,
                "Twelve city-bound packs are executions of twelve shared method designs; city "
                "bindings are not counted as new non-duplicative designs.",
                "Planning-support output does not authorize implementation or establish impact.",
            ],
        )
        bundles.append(bundle)
        scenario_refs = [f"packs/{item.pack.pack_id}/pack.json" for item in compiled]
        entries.append(
            TierDRegistryEntry(
                selection_order=city.spec.selection_order,
                city_id=city.spec.city_id,
                display_name=city.spec.display_name,
                platform=city.spec.source.platform.value,
                bundle_ref=f"cities/{city.spec.city_id}/bundle.json",
                bundle_hash=bundle.content_hash(),
                scenario_pack_refs=scenario_refs,
                scenario_pack_hashes=[item.pack.content_hash() for item in compiled],
                completed_scenarios=sum(
                    item.pack.status is DeepScenarioStatus.COMPLETED for item in compiled
                ),
                negative_scenarios=sum(
                    item.pack.status is not DeepScenarioStatus.COMPLETED for item in compiled
                ),
                underlying_request_count=city.request_count,
                quality_status=quality.overall_status,
            )
        )
        evidence_rows.extend(_scenario_evidence(item) for item in compiled)
    registry = TierDRegistry(
        registry_id="tier-d-deep-cities.2025-reference.v1",
        created_at=created_at,
        reference_period_start=cities[0].start,
        reference_period_end_exclusive=cities[0].end_exclusive,
        selection_method=(
            "Select eight U.S. cities with official bounded 2025 service-request data across "
            "Socrata, CKAN DataStore, and CARTO SQL; require four reconciled privacy-minimized "
            "aggregate views, an exact Census incorporated-place population row and legal "
            "boundary, and a complete six-parameter NASA POWER point series."
        ),
        scenario_templates=list(DEEP_SCENARIO_TEMPLATES),
        entries=entries,
        total_underlying_requests=sum(item.request_count for item in cities),
        platform_counts=dict(
            sorted(Counter(city.spec.source.platform.value for city in cities).items())
        ),
        limitations=[
            "Selection optimizes reproducibility and source-platform heterogeneity, not global "
            "representativeness or policy priority.",
            "The 96 city-bound executions correspond to twelve non-duplicative scenario designs.",
            "Service requests, gridded climate, legal boundaries, and ACS estimates do not provide "
            "validated intervention effects or implementation outcomes.",
        ],
    )
    unique_manifests: dict[str, SourceManifest] = {}
    municipal_ids = {city.spec.source.source_id for city in cities}
    for city in cities:
        for manifest in city.source_manifests:
            existing = unique_manifests.setdefault(manifest.artifact_id, manifest)
            if existing != manifest:
                raise AnalysisError(
                    f"Tier-D repeated source manifest differs: {manifest.artifact_id}"
                )
    if len(unique_manifests) != 49:
        raise AnalysisError("Tier-D compilation must bind exactly 49 deduplicated source artifacts")
    distinct_source_ids = {item.source_id for item in unique_manifests.values()}
    if len(distinct_source_ids) != 11:
        raise AnalysisError("Tier-D compilation must bind exactly eleven distinct source datasets")
    completed = sum(item.status is DeepScenarioStatus.COMPLETED for item in evidence_rows)
    negative = len(evidence_rows) - completed
    evidence_summary = TierDEvidenceSummary(
        summary_id="tier-d-deep-city-evidence.2025-reference.v1",
        created_at=created_at,
        source_artifact_hashes={
            key: value.content_hash for key, value in sorted(unique_manifests.items())
        },
        aggregate_source_rows=sum(
            manifest.record_count
            for manifest in unique_manifests.values()
            if manifest.source_id in municipal_ids
        ),
        context_source_units=sum(
            manifest.record_count
            for manifest in unique_manifests.values()
            if manifest.source_id not in municipal_ids
        ),
        deduplicated_underlying_requests=sum(item.request_count for item in cities),
        scenarios=evidence_rows,
        completed_scenarios=completed,
        negative_scenarios=negative,
        forecast_runs=completed,
        total_forecast_input_observations=sum(
            item.forecast_input_observations for item in evidence_rows
        ),
        simulation_runs=completed,
        total_simulation_iterations=sum(item.simulation_iterations for item in evidence_rows),
        optimization_tasks=completed,
        total_optimization_search_space=sum(
            item.optimization_search_space for item in evidence_rows
        ),
        total_optimization_evaluated_plans=sum(
            item.optimization_evaluated_plans for item in evidence_rows
        ),
        total_optimization_feasible_plans=sum(
            item.optimization_feasible_plans for item in evidence_rows
        ),
        uncertainty_runs=completed,
        total_uncertainty_option_draw_values=sum(
            item.uncertainty_option_draw_values for item in evidence_rows
        ),
        limitations=[
            "Underlying requests are counted once per city even though four aggregate views "
            "independently re-express the same requests.",
            "Ninety-six city bindings are not ninety-six non-duplicative method designs; the "
            "non-duplicative count is twelve.",
            "Simulation iterations, uncertainty draws, optimization plans, and forecast inputs "
            "measure computational work and are not public observations or real interventions.",
            "Public-source reproducibility does not establish external review, deployment, users, "
            "adoption, or real-world impact.",
        ],
    )
    return TierDCompilation(
        source_cities=cities,
        compiled_scenarios=compiled_by_city,
        bundles=bundles,
        registry=registry,
        evidence_summary=evidence_summary,
    )


def _coverage_csv(compilation: TierDCompilation) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "selection_order",
            "city_id",
            "display_name",
            "platform",
            "underlying_requests_deduplicated",
            "aggregate_rows",
            "population_estimate",
            "quality_status",
            "completed_scenarios",
            "negative_scenarios",
            "bundle_hash",
        ]
    )
    bundle_by_id = {item.adapter.city_id: item for item in compilation.bundles}
    city_by_id = {item.spec.city_id: item for item in compilation.source_cities}
    for entry in compilation.registry.entries:
        city = city_by_id[entry.city_id]
        bundle = bundle_by_id[entry.city_id]
        writer.writerow(
            [
                entry.selection_order,
                entry.city_id,
                entry.display_name,
                entry.platform,
                entry.underlying_request_count,
                sum(item.aggregate_row_count for item in city.municipal.values()),
                tier_d_json_value(city.population_row.estimate),
                entry.quality_status.value,
                entry.completed_scenarios,
                entry.negative_scenarios,
                bundle.content_hash(),
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _scenario_ledger_csv(summary: TierDEvidenceSummary) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "pack_id",
            "city_id",
            "template_id",
            "suite",
            "status",
            "observed_request_count",
            "forecast_input_observations",
            "simulation_iterations",
            "optimization_search_space",
            "optimization_evaluated_plans",
            "optimization_feasible_plans",
            "uncertainty_option_draw_values",
            "pack_file_hash",
        ]
    )
    for item in summary.scenarios:
        writer.writerow(
            [
                item.pack_id,
                item.city_id,
                item.scenario_template_id,
                item.suite.value,
                item.status.value,
                item.observed_request_count,
                item.forecast_input_observations,
                item.simulation_iterations,
                item.optimization_search_space,
                item.optimization_evaluated_plans,
                item.optimization_feasible_plans,
                item.uncertainty_option_draw_values,
                item.pack_file_hash,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _source_ledger_csv(compilation: TierDCompilation) -> bytes:
    manifests: dict[str, SourceManifest] = {}
    underlying: dict[str, int] = {}
    city_for_artifact: dict[str, str] = {}
    for city in compilation.source_cities:
        for aggregation in MunicipalAggregation:
            manifest = city.municipal_manifests[aggregation]
            underlying[manifest.artifact_id] = city.request_count
            city_for_artifact[manifest.artifact_id] = city.spec.city_id
        for manifest in city.source_manifests:
            manifests.setdefault(manifest.artifact_id, manifest)
            city_for_artifact.setdefault(manifest.artifact_id, "shared-or-cross-city-context")
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "artifact_id",
            "source_id",
            "city_binding",
            "publisher",
            "declared_source_units",
            "underlying_requests_if_municipal_view",
            "content_hash",
            "retrieved_at",
            "geographic_scope",
            "temporal_scope",
        ]
    )
    for artifact_id, manifest in sorted(manifests.items()):
        writer.writerow(
            [
                artifact_id,
                manifest.source_id,
                city_for_artifact[artifact_id],
                manifest.publisher,
                manifest.record_count,
                underlying.get(artifact_id, "not-applicable"),
                manifest.content_hash,
                manifest.retrieved_at.isoformat(),
                manifest.geographic_scope,
                manifest.temporal_scope,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _metric_ledger_csv(compilation: TierDCompilation) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "city_id",
            "metric_id",
            "value",
            "unit",
            "evidence_type",
            "source_refs",
            "method",
            "interpretation",
        ]
    )
    for bundle in compilation.bundles:
        for metric in bundle.metrics:
            writer.writerow(
                [
                    bundle.adapter.city_id,
                    metric.id,
                    tier_d_json_value(metric.value),
                    metric.unit,
                    metric.evidence_type.value,
                    ";".join(metric.source_refs),
                    metric.method,
                    metric.interpretation,
                ]
            )
    return buffer.getvalue().encode("utf-8")


def _template_catalog_markdown(registry: TierDRegistry) -> bytes:
    lines = [
        "# Tier-D scenario-template catalog",
        "",
        "These are twelve non-duplicative designs. Each is bound once to each of eight cities; "
        "the resulting 96 executions are not counted as 96 unique methods.",
        "",
        "| # | Template | Suite | Completion strategy | Intended claim |",
        "|---:|---|---|---|---|",
    ]
    lines.extend(
        f"| {item.template_order} | `{item.template_id}` | {item.suite.value} | "
        f"{item.completion_strategy.value} | {item.intended_claim} |"
        for item in registry.scenario_templates
    )
    lines.extend(["", "## Universal boundary", ""])
    lines.extend(
        [
            "- A service request is not a verified incident, need, exposure, outcome, or person.",
            "- Proposed coefficients are not observed or causal effects.",
            "- Optimized portfolios are mathematical planning outputs, not city recommendations.",
            "- Negative packs are required outputs when causal or network evidence is absent.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _selection_method_markdown(compilation: TierDCompilation) -> bytes:
    rows = [
        "# Tier-D city and source selection method",
        "",
        compilation.registry.selection_method,
        "",
        "The reference layer intentionally exercises three municipal query platforms: six "
        "Socrata cities, one CKAN DataStore city, and one CARTO SQL city. This is a "
        "reproducibility and schema-heterogeneity choice, not a claim of U.S. or global "
        "representativeness.",
        "",
        "| # | City | Municipal platform | Official local dataset | Request semantics |",
        "|---:|---|---|---|---|",
    ]
    rows.extend(
        f"| {city.spec.selection_order} | {city.spec.display_name} | "
        f"{city.spec.source.platform.value} | `{city.spec.source.dataset_identifier}` | "
        f"{city.spec.source.request_semantics} |"
        for city in compilation.source_cities
    )
    rows.extend(
        [
            "",
            "## Required context for every city",
            "",
            "- Exact 2024 ACS five-year B01003 incorporated-place population row with 90% MOE.",
            "- Exact current TIGERweb incorporated-place legal boundary GEOID.",
            "- Complete 2025-04-01 through 2025-09-30 NASA POWER point series for six parameters.",
            "- Four independent privacy-minimized municipal aggregates that reconcile to one "
            "underlying request total.",
            "",
        ]
    )
    return "\n".join(rows).encode("utf-8")


def _anti_inflation_markdown(compilation: TierDCompilation) -> bytes:
    evidence = compilation.evidence_summary
    four_view_total = evidence.deduplicated_underlying_requests * 4
    lines = [
        "# Tier-D anti-inflation audit",
        "",
        "| Quantity | Audited count | Counting rule |",
        "|---|---:|---|",
        f"| Non-duplicative scenario designs | {evidence.nonduplicative_scenario_designs} | "
        "Count shared templates once. |",
        f"| City-bound scenario executions | {evidence.city_bound_scenario_executions} | "
        "12 templates x 8 cities; not unique methods. |",
        f"| Distinct source datasets | {evidence.distinct_source_datasets} | "
        "8 local datasets plus ACS, TIGERweb, and NASA POWER. |",
        f"| Deduplicated source artifacts | {evidence.source_manifest_artifacts} | "
        "32 municipal views, 8 boundaries, 8 climate points, 1 shared ACS file. |",
        f"| Underlying municipal requests | {evidence.deduplicated_underlying_requests:,} | "
        "Count each city's reconciled total once. |",
        f"| Naive four-view request sum rejected | {four_view_total:,} | "
        "Same requests re-aggregated four ways; never a distinct-request total. |",
        f"| Aggregate source rows | {evidence.aggregate_source_rows:,} | "
        "Endpoint-side grouped rows, not individual requests. |",
        f"| Context source units | {evidence.context_source_units:,} | "
        "8 ACS rows + 8 boundaries + 8 x 1,098 NASA parameter-date values. |",
        f"| Simulation iterations | {evidence.total_simulation_iterations:,} | "
        "Computational draws, not observations. |",
        f"| Optimization plans evaluated | {evidence.total_optimization_evaluated_plans:,} | "
        "Mathematical portfolios, not implemented actions. |",
        f"| Uncertainty option-draw values | "
        f"{evidence.total_uncertainty_option_draw_values:,} | Computational values, not users. |",
        "",
        "No count in this audit establishes external review, domain validity, deployment, users, "
        "municipal adoption, or real-world impact.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _summary_markdown(compilation: TierDCompilation) -> bytes:
    evidence = compilation.evidence_summary
    status_counts = Counter(item.status.value for item in evidence.scenarios)
    suite_counts = Counter(item.suite.value for item in evidence.scenarios)
    lines = [
        "# Tier-D deep-city evidence audit",
        "",
        "## Verified build scope",
        "",
        "- 8 deep-city adapters and 8 city bundles",
        f"- {evidence.nonduplicative_scenario_designs} non-duplicative scenario designs",
        f"- {evidence.city_bound_scenario_executions} city-bound scenario packs and DecisionPacks",
        f"- {evidence.completed_scenarios} completed planning-support packs",
        f"- {evidence.negative_scenarios} explicit insufficient-evidence packs",
        f"- {evidence.source_manifest_artifacts} deduplicated source artifacts from "
        f"{evidence.distinct_source_datasets} datasets",
        f"- {evidence.deduplicated_underlying_requests:,} reconciled underlying municipal requests",
        f"- {evidence.aggregate_source_rows:,} endpoint-side aggregate rows",
        f"- {evidence.context_source_units:,} declared context source units",
        "",
        "## Audited analytical workload",
        "",
        f"- {evidence.forecast_runs} forecast runs over "
        f"{evidence.total_forecast_input_observations:,} daily input positions",
        f"- {evidence.simulation_runs} simulations with "
        f"{evidence.total_simulation_iterations:,} total seeded iterations",
        f"- {evidence.optimization_tasks} exhaustive optimization tasks declaring "
        f"{evidence.total_optimization_search_space:,} portfolios and evaluating "
        f"{evidence.total_optimization_evaluated_plans:,}",
        f"- {evidence.total_optimization_feasible_plans:,} feasible portfolios encountered across "
        "the complete solver task set",
        f"- {evidence.uncertainty_runs} paired uncertainty runs with "
        f"{evidence.total_uncertainty_option_draw_values:,} option-draw values",
        "",
        "## Scenario statuses",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(status_counts.items())],
        "",
        "## Application-suite execution counts",
        "",
        *[f"- `{key}`: {value}" for key, value in sorted(suite_counts.items())],
        "",
        "## Claim boundary",
        "",
        "Completed means the internal public-data planning pipeline ran and validated. It does "
        "not mean policy correctness, causal impact, implementation feasibility, production "
        "deployment, external review, municipal adoption, real users, or real-world impact. "
        "Negative packs deliberately demonstrate that the compiler refuses causal and routing "
        "claims when required evidence is absent.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def write_tier_d_artifacts(
    compilation: TierDCompilation, output_directory: Path
) -> TierDBuildArtifacts:
    """Write all Tier-D artifacts, validate them, and create a portable checksum inventory."""

    if len(compilation.bundles) != 8 or len(compilation.evidence_summary.scenarios) != 96:
        raise AnalysisError("Tier-D compilation does not contain the required 8 cities / 96 packs")
    content: dict[str, bytes] = {
        "registry.json": _model_bytes(compilation.registry),
        "evidence-summary.json": _model_bytes(compilation.evidence_summary),
        "coverage.csv": _coverage_csv(compilation),
        "scenario-ledger.csv": _scenario_ledger_csv(compilation.evidence_summary),
        "source-evidence.csv": _source_ledger_csv(compilation),
        "cross-city-metrics.csv": _metric_ledger_csv(compilation),
        "summary.md": _summary_markdown(compilation),
        "scenario-template-catalog.md": _template_catalog_markdown(compilation.registry),
        "selection-method.md": _selection_method_markdown(compilation),
        "anti-inflation-audit.md": _anti_inflation_markdown(compilation),
    }
    bundle_paths: list[Path] = []
    scenario_pack_paths: list[Path] = []
    bundle_by_id = {item.adapter.city_id: item for item in compilation.bundles}
    for entry in compilation.registry.entries:
        bundle = bundle_by_id[entry.city_id]
        content[entry.bundle_ref] = _model_bytes(bundle)
        bundle_paths.append(output_directory / entry.bundle_ref)
        for compiled, pack_ref in zip(
            compilation.compiled_scenarios[entry.city_id],
            entry.scenario_pack_refs,
            strict=True,
        ):
            content.update(compiled.artifact_bytes)
            content[pack_ref] = _model_bytes(compiled.pack)
            scenario_pack_paths.append(output_directory / pack_ref)
    if len(content) != len(set(content)):
        raise AnalysisError("Tier-D output paths are not unique")
    expected = set(content)
    if output_directory.exists():
        existing = {
            path.relative_to(output_directory).as_posix()
            for path in output_directory.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        }
        unexpected = sorted(existing - expected)
        if unexpected:
            raise AnalysisError(f"Tier-D output contains unrecognized stale files: {unexpected}")
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for relative, payload in sorted(content.items()):
        path = output_directory / relative
        atomic_write(path, payload)
        written.append(path)
    checksum_path = output_directory / "SHA256SUMS"
    checksum_lines = [
        f"{sha256_file(path)[7:]}  {path.relative_to(output_directory).as_posix()}"
        for path in written
    ]
    atomic_write(checksum_path, ("\n".join(checksum_lines) + "\n").encode("ascii"))
    TierDRegistry.model_validate_json((output_directory / "registry.json").read_bytes())
    TierDEvidenceSummary.model_validate_json(
        (output_directory / "evidence-summary.json").read_bytes()
    )
    for path in bundle_paths:
        DeepCityBundle.model_validate_json(path.read_bytes())
    for path in scenario_pack_paths:
        compilation_pack = next(
            item.pack
            for values in compilation.compiled_scenarios.values()
            for item in values
            if item.pack.pack_id == path.parent.name
        )
        if (
            compilation_pack.content_hash()
            != DeepScenarioPack.model_validate_json(path.read_bytes()).content_hash()
        ):
            raise AnalysisError(f"Tier-D pack changed during write: {path}")
    return TierDBuildArtifacts(
        registry_path=output_directory / "registry.json",
        evidence_summary_path=output_directory / "evidence-summary.json",
        coverage_path=output_directory / "coverage.csv",
        scenario_ledger_path=output_directory / "scenario-ledger.csv",
        source_ledger_path=output_directory / "source-evidence.csv",
        metric_ledger_path=output_directory / "cross-city-metrics.csv",
        summary_path=output_directory / "summary.md",
        template_catalog_path=output_directory / "scenario-template-catalog.md",
        selection_method_path=output_directory / "selection-method.md",
        anti_inflation_path=output_directory / "anti-inflation-audit.md",
        checksum_path=checksum_path,
        bundle_paths=bundle_paths,
        scenario_pack_paths=scenario_pack_paths,
        artifact_paths=written,
    )


def build_tier_d_artifacts(source_directory: Path, output_directory: Path) -> TierDBuildArtifacts:
    """Compile and write the full deterministic Tier-D reference layer."""

    return write_tier_d_artifacts(compile_tier_d_reference(source_directory), output_directory)


__all__ = [
    "TierDBuildArtifacts",
    "TierDCompilation",
    "build_tier_d_artifacts",
    "compile_tier_d_reference",
    "write_tier_d_artifacts",
]
