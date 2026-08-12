#!/usr/bin/env python3
"""Independently verify committed protocols, source artifacts, and golden rebuilds."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]


def assert_same(left: Path, right: Path) -> None:
    if left.read_bytes() != right.read_bytes():
        raise RuntimeError(f"golden artifact mismatch: {left.relative_to(ROOT)} != {right.name}")


def verify_checksum(directory: Path) -> None:
    checksum_path = directory / "SHA256SUMS"
    digest, filename = checksum_path.read_text(encoding="ascii").strip().split("  ", 1)
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
    manifest_paths = sorted(ROOT.glob("examples/data/**/*.manifest.json"))
    manifests: list[SourceManifest] = []
    for path in manifest_paths:
        manifest = validate_document(path, SourceManifest)
        manifest.verify_artifact(path.parent)
        manifests.append(manifest)

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
        build_schemas(generated_schema_dir)
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

    statuses = Counter(pack.status.value for pack in packs)
    return {
        "city_adapter_documents": len(city_paths),
        "decision_pack_content_hashes": sorted(pack.content_hash() for pack in packs),
        "decision_packs": len(packs),
        "decision_pack_statuses": dict(sorted(statuses.items())),
        "generated_schemas": 3,
        "rebuilt_reference_hashes": sorted(rebuilt_hashes),
        "rebuilds_exactly_matched": len(rebuilt_hashes),
        "scenario_documents": len(scenario_paths),
        "source_manifest_records": sum(item.record_count for item in manifests),
        "source_manifests": len(manifests),
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
