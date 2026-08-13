#!/usr/bin/env python3
"""Independently verify committed protocols, source artifacts, and golden rebuilds."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath

from civicdecision.analysis.causal import DifferenceInDifferencesRun
from civicdecision.analysis.simulation import SimulationRun
from civicdecision.analysis.uncertainty import UncertaintyRun
from civicdecision.benchmarks.build import (
    build_milestone_4_benchmarks,
    engine_qualification_evidence,
    historical_replay_evidence,
    optimization_task_evidence,
)
from civicdecision.benchmarks.models import (
    BenchmarkEvidenceSummary,
    BenchmarkRegistry,
    EngineQualificationEvidence,
    HistoricalReplay,
    HistoricalReplayEvidence,
    OptimizationTaskEvidence,
)
from civicdecision.connectors.registry import CONNECTOR_REGISTRY, registry_json
from civicdecision.deep.build import build_tier_d_artifacts
from civicdecision.deep.models import (
    DeepCityBundle,
    DeepScenarioPack,
    TierDEvidenceSummary,
    TierDRegistry,
)
from civicdecision.demos.heat_access import (
    HeatAccessDemoConfig,
    build_heat_access_pack,
    write_decision_artifacts,
)
from civicdecision.io import validate_document
from civicdecision.optimization.portfolio import PortfolioOptimizationRun
from civicdecision.protocols.base import StrictModel, sha256_file
from civicdecision.protocols.city import CityAdapterManifest
from civicdecision.protocols.decision import DecisionPack
from civicdecision.protocols.scenario import PolicyScenario
from civicdecision.protocols.schemas import build_schemas
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.city_catalog import (
    GlobalCityCatalog,
    build_global_city_catalog,
    write_catalog_artifacts,
)
from civicdecision.semantic.core import SemanticBundle
from civicdecision.semantic.graph import UrbanGraphBundle
from civicdecision.standardized.build import build_tier_s_registry, write_tier_s_artifacts
from civicdecision.standardized.models import (
    QualityStatus,
    StandardizedCityBundle,
    StandardScenarioRun,
    TierSRegistry,
)

ROOT = Path(__file__).resolve().parents[1]


def assert_same(left: Path, right: Path) -> None:
    if left.read_bytes() != right.read_bytes():
        raise RuntimeError(f"golden artifact mismatch: {left.relative_to(ROOT)} != {right.name}")


def assert_tree_same(expected: Path, actual: Path) -> None:
    expected_files = sorted(
        path.relative_to(expected) for path in expected.rglob("*") if path.is_file()
    )
    actual_files = sorted(path.relative_to(actual) for path in actual.rglob("*") if path.is_file())
    if expected_files != actual_files:
        raise RuntimeError("golden artifact tree contains missing or unexpected files")
    for relative in expected_files:
        assert_same(expected / relative, actual / relative)


def safe_relative_artifact(directory: Path, filename: str) -> Path:
    relative = PurePosixPath(filename)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in filename:
        raise RuntimeError(f"checksum path is not a safe relative POSIX path: {filename}")
    artifact = (directory / Path(*relative.parts)).resolve()
    if not artifact.is_relative_to(directory.resolve()) or not artifact.is_file():
        raise RuntimeError(f"checksum target is missing or escapes its directory: {filename}")
    return artifact


def verify_checksum(directory: Path) -> None:
    checksum_path = directory / "SHA256SUMS"
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise RuntimeError(f"empty checksum file: {checksum_path.relative_to(ROOT)}")
    seen: set[str] = set()
    for line in lines:
        try:
            digest, filename = line.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError(f"invalid checksum line: {line}") from exc
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise RuntimeError(f"invalid SHA-256 digest in {checksum_path.relative_to(ROOT)}")
        if filename in seen:
            raise RuntimeError(f"duplicate checksum target: {filename}")
        seen.add(filename)
        artifact = safe_relative_artifact(directory, filename)
        if sha256_file(artifact)[7:] != digest:
            raise RuntimeError(f"checksum mismatch: {checksum_path.relative_to(ROOT)}")
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if seen != actual_files:
        missing = sorted(actual_files - seen)
        stale = sorted(seen - actual_files)
        raise RuntimeError(f"checksum inventory is incomplete: unlisted={missing}, missing={stale}")


def rebuild_reference_workflow(
    data: Path,
    manifest: Path,
    scenario: Path,
    config_path: Path,
    expected_output: Path,
    temporary_root: Path,
) -> str:
    config = validate_document(config_path, HeatAccessDemoConfig)
    pack = build_heat_access_pack(
        data,
        manifest,
        scenario,
        config,
        config_reference=config_path,
    )
    actual_output = temporary_root / expected_output.name
    write_decision_artifacts(pack, actual_output)
    for filename in ("decision-pack.json", "decision-brief.md", "SHA256SUMS"):
        assert_same(expected_output / filename, actual_output / filename)
    return pack.content_hash()


def verify_repository() -> dict[str, object]:
    catalog_path = ROOT / "catalog/connectors.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog != json.loads(registry_json()):
        raise RuntimeError("committed connector catalog does not match the code registry")
    manifest_paths = sorted(ROOT.glob("examples/data/**/*.manifest.json"))
    manifests: list[SourceManifest] = []
    for path in manifest_paths:
        manifest = validate_document(path, SourceManifest)
        manifest.verify_artifact(path.parent)
        manifests.append(manifest)
    attribution = (ROOT / "docs/DATA_ATTRIBUTION.md").read_text(encoding="utf-8")
    missing_attributions = sorted(
        {
            manifest.source_id
            for manifest in manifests
            if f"`{manifest.source_id}`" not in attribution
        }
    )
    if missing_attributions:
        raise RuntimeError(f"missing source attribution entries: {missing_attributions}")
    manifests_by_artifact = {item.artifact_id: item for item in manifests}
    if len(manifests_by_artifact) != len(manifests):
        raise RuntimeError("source manifest artifact identifiers are not globally unique")

    city_paths = sorted(ROOT.glob("examples/cities/*.yaml"))
    for path in city_paths:
        validate_document(path, CityAdapterManifest)
    scenario_paths = sorted(ROOT.glob("examples/scenarios/*.yaml"))
    for path in scenario_paths:
        validate_document(path, PolicyScenario)

    output_paths = sorted(ROOT.glob("examples/outputs/*/decision-pack.json"))
    packs = [validate_document(path, DecisionPack) for path in output_paths]
    for path in output_paths:
        verify_checksum(path.parent)

    global_catalog_dir = ROOT / "catalog/global-cities"
    global_catalog = validate_document(global_catalog_dir / "cities-tier-g.json", GlobalCityCatalog)
    semantic_bundle = validate_document(
        global_catalog_dir / "cities-tier-g.semantic.json", SemanticBundle
    )
    seed_graph = validate_document(
        global_catalog_dir / "cities-tier-g.graph.json", UrbanGraphBundle
    )
    verify_checksum(global_catalog_dir)
    coverage_path = global_catalog_dir / "cities-tier-g.coverage.csv"
    with coverage_path.open(encoding="utf-8", newline="") as handle:
        coverage_reader = csv.DictReader(handle)
        expected_fields = [
            "selection_rank",
            "city_id",
            "name",
            "country_code",
            "timezone",
            "latitude",
            "longitude",
            "source_population",
            "selection_basis",
            "source_modification_date",
        ]
        if coverage_reader.fieldnames != expected_fields:
            raise RuntimeError("global city coverage matrix header does not match the contract")
        coverage_rows = list(coverage_reader)
    if len(coverage_rows) != global_catalog.target_count:
        raise RuntimeError("global city coverage matrix row count does not match the catalog")
    for row, city in zip(coverage_rows, global_catalog.cities, strict=True):
        if (
            int(row["selection_rank"]) != city.selection_rank
            or row["city_id"] != city.city_id
            or row["country_code"] != city.country_code
            or int(row["source_population"]) != city.source_population
            or row["selection_basis"] != city.selection_basis
        ):
            raise RuntimeError(f"global city coverage row differs at rank {city.selection_rank}")

    standardized_dir = ROOT / "catalog/standardized-cities"
    tier_s_registry = validate_document(standardized_dir / "registry.json", TierSRegistry)
    verify_checksum(standardized_dir)
    tier_s_bundles: list[StandardizedCityBundle] = []
    tier_s_runs: list[StandardScenarioRun] = []
    for entry in tier_s_registry.entries:
        bundle_path = safe_relative_artifact(standardized_dir, entry.bundle_ref)
        bundle = validate_document(bundle_path, StandardizedCityBundle)
        if bundle.content_hash() != entry.bundle_hash:
            raise RuntimeError(f"Tier-S bundle hash mismatch: {entry.city_id}")
        for embedded in bundle.source_manifests:
            if manifests_by_artifact.get(embedded.artifact_id) != embedded:
                raise RuntimeError(
                    f"Tier-S bundle embeds an unknown source: {embedded.artifact_id}"
                )
        for index, reference in enumerate(entry.run_refs):
            run_path = safe_relative_artifact(standardized_dir, reference)
            run = validate_document(run_path, StandardScenarioRun)
            if run != bundle.scenario_runs[index] or run.content_hash() != entry.run_hashes[index]:
                raise RuntimeError(f"Tier-S scenario run mismatch: {reference}")
            tier_s_runs.append(run)
        tier_s_bundles.append(bundle)
    tier_s_coverage_path = standardized_dir / "coverage.csv"
    with tier_s_coverage_path.open(encoding="utf-8", newline="") as handle:
        tier_s_coverage_reader = csv.DictReader(handle)
        tier_s_coverage_rows = list(tier_s_coverage_reader)
    if len(tier_s_coverage_rows) != tier_s_registry.target_count:
        raise RuntimeError("Tier-S coverage matrix row count does not match the registry")
    for row, entry in zip(tier_s_coverage_rows, tier_s_registry.entries, strict=True):
        if (
            int(row["selection_order"]) != entry.selection_order
            or row["city_id"] != entry.city_id
            or row["bundle_hash"] != entry.bundle_hash
        ):
            raise RuntimeError(f"Tier-S coverage row differs for {entry.city_id}")
    tier_s_comparison_path = standardized_dir / "cross-city-comparison.csv"
    with tier_s_comparison_path.open(encoding="utf-8", newline="") as handle:
        tier_s_comparison_rows = list(csv.DictReader(handle))
    if len(tier_s_comparison_rows) != tier_s_registry.target_count:
        raise RuntimeError("Tier-S comparison row count does not match the registry")
    if any(int(row["recommendations_issued"]) != 0 for row in tier_s_comparison_rows):
        raise RuntimeError("Tier-S comparison cannot contain issued recommendations")

    benchmark_dir = ROOT / "benchmarks/milestone-4"
    benchmark_registry = validate_document(benchmark_dir / "registry.json", BenchmarkRegistry)
    benchmark_evidence_path = safe_relative_artifact(
        benchmark_dir, benchmark_registry.evidence_summary_ref
    )
    benchmark_evidence = validate_document(benchmark_evidence_path, BenchmarkEvidenceSummary)
    if sha256_file(benchmark_evidence_path) != benchmark_registry.evidence_summary_content_hash:
        raise RuntimeError("benchmark evidence summary hash mismatch")
    if benchmark_evidence.artifact_set_hash != benchmark_registry.artifact_set_hash:
        raise RuntimeError("benchmark evidence artifact-set hash mismatch")
    verify_checksum(benchmark_dir)
    benchmark_replays: list[HistoricalReplay] = []
    benchmark_optimizations: list[PortfolioOptimizationRun] = []
    reconstructed_replay_evidence: list[HistoricalReplayEvidence] = []
    reconstructed_optimization_evidence: list[OptimizationTaskEvidence] = []
    reconstructed_qualification_evidence: list[EngineQualificationEvidence] = []
    replay_evidence_by_id = {item.replay_id: item for item in benchmark_evidence.historical_replays}
    optimization_evidence_by_id = {
        item.run_id: item for item in benchmark_evidence.optimization_tasks
    }
    qualification_evidence_by_id = {
        item.artifact_id: item for item in benchmark_evidence.engine_qualification_runs
    }
    for artifact in benchmark_registry.artifacts:
        path = safe_relative_artifact(benchmark_dir, artifact.relative_path)
        if sha256_file(path) != artifact.content_hash:
            raise RuntimeError(f"benchmark artifact hash mismatch: {artifact.artifact_id}")
        if artifact.kind == "historical-replay":
            replay = validate_document(path, HistoricalReplay)
            benchmark_replays.append(replay)
            replay_evidence_row = historical_replay_evidence(replay, artifact.content_hash)
            if replay_evidence_row != replay_evidence_by_id.get(artifact.artifact_id):
                raise RuntimeError(f"benchmark replay evidence differs: {artifact.artifact_id}")
            reconstructed_replay_evidence.append(replay_evidence_row)
        elif artifact.kind == "optimization-task":
            optimization = validate_document(path, PortfolioOptimizationRun)
            benchmark_optimizations.append(optimization)
            optimization_evidence_row = optimization_task_evidence(
                optimization, artifact.content_hash
            )
            if optimization_evidence_row != optimization_evidence_by_id.get(artifact.artifact_id):
                raise RuntimeError(
                    f"benchmark optimization evidence differs: {artifact.artifact_id}"
                )
            reconstructed_optimization_evidence.append(optimization_evidence_row)
        else:
            qualification_run: StrictModel
            if artifact.artifact_id.startswith("qualification-causal"):
                qualification_run = validate_document(path, DifferenceInDifferencesRun)
            elif artifact.artifact_id == "qualification-simulation-seeded":
                qualification_run = validate_document(path, SimulationRun)
            elif artifact.artifact_id.startswith("qualification-uncertainty"):
                qualification_run = validate_document(path, UncertaintyRun)
            else:
                raise RuntimeError(
                    f"unknown benchmark qualification artifact: {artifact.artifact_id}"
                )
            qualification_evidence_row = engine_qualification_evidence(
                artifact_id=artifact.artifact_id,
                run=qualification_run,
                source_refs=artifact.source_refs,
                content_hash=artifact.content_hash,
            )
            if qualification_evidence_row != qualification_evidence_by_id.get(artifact.artifact_id):
                raise RuntimeError(
                    f"benchmark qualification evidence differs: {artifact.artifact_id}"
                )
            reconstructed_qualification_evidence.append(qualification_evidence_row)
    if (
        reconstructed_replay_evidence != benchmark_evidence.historical_replays
        or reconstructed_optimization_evidence != benchmark_evidence.optimization_tasks
        or reconstructed_qualification_evidence != benchmark_evidence.engine_qualification_runs
    ):
        raise RuntimeError("benchmark evidence row order differs from the registry order")

    deep_dir = ROOT / "catalog/deep-cities"
    tier_d_registry = validate_document(deep_dir / "registry.json", TierDRegistry)
    tier_d_evidence = validate_document(deep_dir / "evidence-summary.json", TierDEvidenceSummary)
    verify_checksum(deep_dir)
    tier_d_bundles: list[DeepCityBundle] = []
    tier_d_packs: list[DeepScenarioPack] = []
    tier_d_evidence_by_id = {item.pack_id: item for item in tier_d_evidence.scenarios}
    tier_d_source_paths = sorted((ROOT / "examples/data/tier-d").glob("**/*.manifest.json"))
    tier_d_source_manifests = {
        validate_document(path, SourceManifest).artifact_id: validate_document(path, SourceManifest)
        for path in tier_d_source_paths
    }
    if len(tier_d_source_manifests) != tier_d_evidence.source_manifest_artifacts:
        raise RuntimeError("Tier-D source artifact count differs from the evidence summary")
    if tier_d_evidence.source_artifact_hashes != {
        key: value.content_hash for key, value in sorted(tier_d_source_manifests.items())
    }:
        raise RuntimeError("Tier-D source artifact hashes differ from the evidence summary")
    for tier_d_entry in tier_d_registry.entries:
        tier_d_bundle_path = safe_relative_artifact(deep_dir, tier_d_entry.bundle_ref)
        tier_d_bundle = validate_document(tier_d_bundle_path, DeepCityBundle)
        if tier_d_bundle.content_hash() != tier_d_entry.bundle_hash:
            raise RuntimeError(f"Tier-D bundle hash mismatch: {tier_d_entry.city_id}")
        for embedded in tier_d_bundle.source_manifests:
            if manifests_by_artifact.get(embedded.artifact_id) != embedded:
                raise RuntimeError(
                    f"Tier-D bundle embeds an unknown source: {embedded.artifact_id}"
                )
        for index, reference in enumerate(tier_d_entry.scenario_pack_refs):
            pack_path = safe_relative_artifact(deep_dir, reference)
            pack = validate_document(pack_path, DeepScenarioPack)
            if (
                pack != tier_d_bundle.scenario_packs[index]
                or pack.content_hash() != tier_d_entry.scenario_pack_hashes[index]
            ):
                raise RuntimeError(f"Tier-D scenario pack mismatch: {reference}")
            evidence_row = tier_d_evidence_by_id.get(pack.pack_id)
            if evidence_row is None or evidence_row.pack_file_hash != sha256_file(pack_path):
                raise RuntimeError(f"Tier-D scenario evidence mismatch: {pack.pack_id}")
            for scenario_artifact in pack.analytical_artifacts:
                artifact_path = safe_relative_artifact(deep_dir, scenario_artifact.path)
                if (
                    sha256_file(artifact_path) != scenario_artifact.content_hash
                    or evidence_row.artifact_hashes.get(scenario_artifact.kind)
                    != scenario_artifact.content_hash
                ):
                    raise RuntimeError(
                        f"Tier-D analytical artifact hash mismatch: {scenario_artifact.path}"
                    )
            tier_d_packs.append(pack)
        tier_d_bundles.append(tier_d_bundle)
    if len(tier_d_packs) != 96 or len(tier_d_bundles) != 8:
        raise RuntimeError("Tier-D verified city/pack count differs from 8 / 96")
    if set(tier_d_evidence_by_id) != {item.pack_id for item in tier_d_packs}:
        raise RuntimeError("Tier-D evidence summary does not exactly cover scenario packs")
    tier_d_coverage_path = deep_dir / "coverage.csv"
    with tier_d_coverage_path.open(encoding="utf-8", newline="") as handle:
        tier_d_coverage_rows = list(csv.DictReader(handle))
    if len(tier_d_coverage_rows) != 8:
        raise RuntimeError("Tier-D coverage matrix must contain eight city rows")
    tier_d_scenario_ledger_path = deep_dir / "scenario-ledger.csv"
    with tier_d_scenario_ledger_path.open(encoding="utf-8", newline="") as handle:
        tier_d_scenario_rows = list(csv.DictReader(handle))
    if len(tier_d_scenario_rows) != 96:
        raise RuntimeError("Tier-D scenario ledger must contain 96 rows")
    tier_d_source_ledger_path = deep_dir / "source-evidence.csv"
    with tier_d_source_ledger_path.open(encoding="utf-8", newline="") as handle:
        tier_d_source_rows = list(csv.DictReader(handle))
    if len(tier_d_source_rows) != 49:
        raise RuntimeError("Tier-D source ledger must contain 49 deduplicated rows")
    tier_d_metric_ledger_path = deep_dir / "cross-city-metrics.csv"
    with tier_d_metric_ledger_path.open(encoding="utf-8", newline="") as handle:
        tier_d_metric_rows = list(csv.DictReader(handle))
    if len(tier_d_metric_rows) != sum(len(item.metrics) for item in tier_d_bundles):
        raise RuntimeError("Tier-D metric ledger does not cover every embedded metric")

    cdc_dir = ROOT / "examples/data/cdc-places"
    data = cdc_dir / "cdc-places-7ccf6e7d6dc3.json"
    cdc_manifest_path = cdc_dir / "cdc-places-7ccf6e7d6dc3.manifest.json"
    scenario = ROOT / "examples/scenarios/suffolk-heat-access-demo.yaml"
    workflows = [
        (
            ROOT / "examples/configs/suffolk-heat-access-default.yaml",
            ROOT / "examples/outputs/suffolk-heat-access",
        ),
        (
            ROOT / "examples/configs/suffolk-heat-access-infeasible.yaml",
            ROOT / "examples/outputs/suffolk-heat-access-infeasible",
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="civicdecision-verify-") as temporary:
        temporary_root = Path(temporary)
        generated_schema_dir = temporary_root / "schemas"
        generated_schemas = build_schemas(generated_schema_dir)
        for generated in sorted(generated_schema_dir.glob("*.schema.json")):
            assert_same(ROOT / "schemas" / generated.name, generated)
        rebuilt_hashes = [
            rebuild_reference_workflow(
                data,
                cdc_manifest_path,
                scenario,
                config,
                output,
                temporary_root,
            )
            for config, output in workflows
        ]
        geonames_manifests = sorted((ROOT / "examples/data/geonames").glob("*.manifest.json"))
        if len(geonames_manifests) != 1:
            raise RuntimeError("expected exactly one committed GeoNames manifest")
        rebuilt_city_catalog = build_global_city_catalog(
            geonames_manifests[0], global_catalog.target_count
        )
        rebuilt_city_dir = temporary_root / "global-cities"
        write_catalog_artifacts(rebuilt_city_catalog, rebuilt_city_dir)
        for filename in (
            "cities-tier-g.json",
            "cities-tier-g.coverage.csv",
            "cities-tier-g.semantic.json",
            "cities-tier-g.graph.json",
            "SHA256SUMS",
        ):
            assert_same(global_catalog_dir / filename, rebuilt_city_dir / filename)
        rebuilt_tier_s_registry, rebuilt_tier_s_bundles = build_tier_s_registry(
            global_catalog_dir / "cities-tier-g.json",
            ROOT / "examples/data/tier-s/nasa-power",
            ROOT / "examples/data/tier-s/world-bank",
            tier_s_registry.target_count,
        )
        rebuilt_tier_s_dir = temporary_root / "standardized-cities"
        write_tier_s_artifacts(
            rebuilt_tier_s_registry,
            rebuilt_tier_s_bundles,
            rebuilt_tier_s_dir,
        )
        assert_tree_same(standardized_dir, rebuilt_tier_s_dir)
        rebuilt_benchmark_dir = temporary_root / "milestone-4"
        build_milestone_4_benchmarks(
            standardized_directory=standardized_dir,
            nasa_source_directory=ROOT / "examples/data/tier-s/nasa-power",
            output_directory=rebuilt_benchmark_dir,
            replay_city_count=20,
            optimization_task_count=100,
        )
        assert_tree_same(benchmark_dir, rebuilt_benchmark_dir)
        rebuilt_tier_d_dir = temporary_root / "deep-cities"
        build_tier_d_artifacts(
            ROOT / "examples/data/tier-d",
            rebuilt_tier_d_dir,
        )
        assert_tree_same(deep_dir, rebuilt_tier_d_dir)

    statuses = Counter(pack.status.value for pack in packs)
    connector_families = Counter(item.family.value for item in CONNECTOR_REGISTRY)
    tier_s_statuses = Counter(item.status.value for item in tier_s_runs)
    benchmark_statuses = Counter(item.status for item in benchmark_registry.artifacts)
    tier_d_statuses = Counter(item.status.value for item in tier_d_packs)
    tier_d_suites = Counter(item.suite.value for item in tier_d_packs)
    tier_s_nasa_records = sum(
        manifest.record_count
        for path, manifest in zip(manifest_paths, manifests, strict=True)
        if path.is_relative_to(ROOT / "examples/data/tier-s/nasa-power")
    )
    tier_s_context_records = sum(
        manifest.record_count
        for path, manifest in zip(manifest_paths, manifests, strict=True)
        if path.is_relative_to(ROOT / "examples/data/tier-s/world-bank")
    )
    inspection_ranks = {1, 2, 3, 25, 50, 75, 100, 125, 150, 175, 200, 225, 244, 245, 250}
    inspected_cities = [
        {
            "city_id": item.city_id,
            "country_code": item.country_code,
            "name": item.name,
            "selection_basis": item.selection_basis,
            "selection_rank": item.selection_rank,
            "source_population": item.source_population,
        }
        for item in global_catalog.cities
        if item.selection_rank in inspection_ranks
    ]
    return {
        "benchmark_artifacts": len(benchmark_registry.artifacts),
        "benchmark_artifact_set_hash": benchmark_registry.artifact_set_hash,
        "benchmark_baseline_comparisons": benchmark_evidence.baseline_comparisons,
        "benchmark_checksum_entries": len(
            (benchmark_dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        ),
        "benchmark_engine_qualification_runs": benchmark_registry.engine_qualification_runs,
        "benchmark_evidence_summary_content_hash": (
            benchmark_registry.evidence_summary_content_hash
        ),
        "benchmark_exactly_rebuilt": True,
        "benchmark_historical_replays": len(benchmark_replays),
        "benchmark_method_counts": benchmark_evidence.method_counts,
        "benchmark_optimization_feasible_plans": benchmark_evidence.total_feasible_plans,
        "benchmark_optimization_portfolios_evaluated": (benchmark_evidence.total_evaluated_plans),
        "benchmark_optimization_search_space": benchmark_evidence.total_search_space_size,
        "benchmark_optimization_status_counts": benchmark_evidence.optimization_status_counts,
        "benchmark_optimization_strategy_counts": benchmark_evidence.optimization_strategy_counts,
        "benchmark_optimization_tasks": len(benchmark_optimizations),
        "benchmark_parameter_counts": benchmark_evidence.parameter_counts,
        "benchmark_registry_content_hash": benchmark_registry.content_hash(),
        "benchmark_statuses": dict(sorted(benchmark_statuses.items())),
        "city_adapter_documents": len(city_paths),
        "connector_families": dict(sorted(connector_families.items())),
        "connectors": len(CONNECTOR_REGISTRY),
        "decision_pack_content_hashes": sorted(pack.content_hash() for pack in packs),
        "decision_packs": len(packs),
        "decision_pack_statuses": dict(sorted(statuses.items())),
        "generated_schemas": len(generated_schemas),
        "global_city_catalog_content_hash": global_catalog.content_hash(),
        "global_city_catalog_exactly_rebuilt": True,
        "global_city_country_or_territory_codes": global_catalog.country_or_territory_count,
        "global_city_country_leaders": sum(
            item.selection_basis == "country-leader" for item in global_catalog.cities
        ),
        "global_city_coverage_matrix_rows": len(coverage_rows),
        "global_city_population_source_zero_count": sum(
            item.source_population == 0 for item in global_catalog.cities
        ),
        "global_city_timezones": len({item.timezone for item in global_catalog.cities}),
        "global_tier_g_cities": len(global_catalog.cities),
        "global_tier_g_inspection_sample": inspected_cities,
        "seed_graph_content_hash": seed_graph.content_hash(),
        "seed_graph_edges": len(seed_graph.edges),
        "seed_graph_nodes": len(seed_graph.nodes),
        "semantic_geographies": len(semantic_bundle.geographies),
        "rebuilt_reference_hashes": sorted(rebuilt_hashes),
        "rebuilds_exactly_matched": len(rebuilt_hashes),
        "scenario_documents": len(scenario_paths),
        "source_manifest_records": sum(item.record_count for item in manifests),
        "source_manifests": len(manifests),
        "source_attributions": len({item.source_id for item in manifests}),
        "tier_s_bundle_metrics": sum(len(item.metrics) for item in tier_s_bundles),
        "tier_s_city_bundles": len(tier_s_bundles),
        "tier_s_checksum_entries": len(
            (standardized_dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        ),
        "tier_s_country_context_records": tier_s_context_records,
        "tier_s_cross_city_comparison_csv_hash": sha256_file(tier_s_comparison_path),
        "tier_s_cross_city_comparison_markdown_hash": sha256_file(
            standardized_dir / "cross-city-comparison.md"
        ),
        "tier_s_cross_city_comparison_rows": len(tier_s_comparison_rows),
        "tier_s_coverage_matrix_rows": len(tier_s_coverage_rows),
        "tier_s_exactly_rebuilt": True,
        "tier_s_exclusions_before_target": len(tier_s_registry.exclusions_before_target),
        "tier_s_nasa_parameter_date_values": tier_s_nasa_records,
        "tier_s_quality_passes": sum(
            item.quality_report.overall_status is QualityStatus.PASS for item in tier_s_bundles
        ),
        "tier_s_registry_content_hash": tier_s_registry.content_hash(),
        "tier_s_scenario_runs": len(tier_s_runs),
        "tier_s_scenario_statuses": dict(sorted(tier_s_statuses.items())),
        "tier_s_source_bindings": sum(len(item.source_bindings) for item in tier_s_bundles),
        "tier_d_aggregate_source_rows": tier_d_evidence.aggregate_source_rows,
        "tier_d_bundle_metrics": sum(len(item.metrics) for item in tier_d_bundles),
        "tier_d_checksum_entries": len(
            (deep_dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        ),
        "tier_d_city_bundles": len(tier_d_bundles),
        "tier_d_context_source_units": tier_d_evidence.context_source_units,
        "tier_d_decision_briefs": tier_d_evidence.decision_briefs,
        "tier_d_decision_packs": tier_d_evidence.decision_packs,
        "tier_d_deduplicated_underlying_requests": (
            tier_d_evidence.deduplicated_underlying_requests
        ),
        "tier_d_distinct_source_datasets": tier_d_evidence.distinct_source_datasets,
        "tier_d_evidence_summary_content_hash": sha256_file(deep_dir / "evidence-summary.json"),
        "tier_d_exactly_rebuilt": True,
        "tier_d_forecast_input_observations": (tier_d_evidence.total_forecast_input_observations),
        "tier_d_forecast_runs": tier_d_evidence.forecast_runs,
        "tier_d_nonduplicative_scenario_designs": (tier_d_evidence.nonduplicative_scenario_designs),
        "tier_d_optimization_evaluated_plans": (tier_d_evidence.total_optimization_evaluated_plans),
        "tier_d_optimization_feasible_plans": (tier_d_evidence.total_optimization_feasible_plans),
        "tier_d_optimization_search_space": tier_d_evidence.total_optimization_search_space,
        "tier_d_optimization_tasks": tier_d_evidence.optimization_tasks,
        "tier_d_quality_passes": sum(
            item.quality_report.overall_status is QualityStatus.PASS for item in tier_d_bundles
        ),
        "tier_d_quality_warnings": sum(
            item.quality_report.overall_status is QualityStatus.WARN for item in tier_d_bundles
        ),
        "tier_d_registry_content_hash": tier_d_registry.content_hash(),
        "tier_d_scenario_packs": len(tier_d_packs),
        "tier_d_scenario_statuses": dict(sorted(tier_d_statuses.items())),
        "tier_d_simulation_iterations": tier_d_evidence.total_simulation_iterations,
        "tier_d_simulation_runs": tier_d_evidence.simulation_runs,
        "tier_d_source_artifacts": tier_d_evidence.source_manifest_artifacts,
        "tier_d_suite_execution_counts": dict(sorted(tier_d_suites.items())),
        "tier_d_uncertainty_option_draw_values": (
            tier_d_evidence.total_uncertainty_option_draw_values
        ),
        "tier_d_uncertainty_runs": tier_d_evidence.uncertainty_runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify_repository()
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
