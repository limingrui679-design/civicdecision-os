#!/usr/bin/env python3
"""Independently verify committed protocols, source artifacts, and golden rebuilds."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import Counter
from pathlib import Path

from civicdecision.connectors.registry import CONNECTOR_REGISTRY, registry_json
from civicdecision.demos.heat_access import (
    HeatAccessDemoConfig,
    build_heat_access_pack,
    write_decision_artifacts,
)
from civicdecision.io import validate_document
from civicdecision.protocols.base import sha256_file
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

ROOT = Path(__file__).resolve().parents[1]


def assert_same(left: Path, right: Path) -> None:
    if left.read_bytes() != right.read_bytes():
        raise RuntimeError(f"golden artifact mismatch: {left.relative_to(ROOT)} != {right.name}")


def verify_checksum(directory: Path) -> None:
    checksum_path = directory / "SHA256SUMS"
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise RuntimeError(f"empty checksum file: {checksum_path.relative_to(ROOT)}")
    for line in lines:
        digest, filename = line.split("  ", 1)
        artifact = directory / filename
        if sha256_file(artifact)[7:] != digest:
            raise RuntimeError(f"checksum mismatch: {checksum_path.relative_to(ROOT)}")
        if Path(filename).is_absolute() or "/" in filename:
            raise RuntimeError(f"checksum path is not portable: {filename}")


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

    cdc_dir = ROOT / "examples/data/cdc-places"
    data = cdc_dir / "cdc-places-7ccf6e7d6dc3.json"
    manifest = cdc_dir / "cdc-places-7ccf6e7d6dc3.manifest.json"
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
                manifest,
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

    statuses = Counter(pack.status.value for pack in packs)
    connector_families = Counter(item.family.value for item in CONNECTOR_REGISTRY)
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
