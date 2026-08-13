"""Deterministic product-surface artifact builder."""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, model_validator

from civicdecision import __version__
from civicdecision.api import create_app
from civicdecision.connectors.base import atomic_write
from civicdecision.errors import IntegrityError
from civicdecision.plugins.models import PluginManifest, PluginPackage, PluginPackageSummary
from civicdecision.product.models import (
    BenchmarkOverview,
    CatalogSummary,
    CityDetail,
    CityPage,
    CitySummary,
    ProductHealth,
    ScenarioDesignDetail,
    ScenarioDesignPage,
    ScenarioDesignSummary,
    ScenarioDetail,
    ScenarioFamilyDetail,
    ScenarioFamilyPage,
    ScenarioFamilySummary,
    ScenarioKind,
    ScenarioLibraryEvidence,
    ScenarioPage,
    ScenarioSummary,
    SourcePage,
    SourceSummary,
    SuiteOverview,
)
from civicdecision.product.store import ArtifactStore
from civicdecision.protocols.base import StrictModel, sha256_file
from civicdecision.scenario_library.models import (
    DecisionType,
    ImplementationStatus,
    ScenarioDesign,
    ScenarioFamily,
    ScenarioLibraryAudit,
    ScenarioLibraryRegistry,
)


class ProductArtifactEntry(StrictModel):
    path: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]*$")
    media_type: str = Field(min_length=1)
    byte_count: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    record_count: int | None = Field(default=None, ge=0)


class ProductArtifactManifest(StrictModel):
    schema_version: str = "1.0.0"
    software_version: str = Field(min_length=1)
    catalog_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_count: int = Field(ge=1)
    artifacts: list[ProductArtifactEntry] = Field(min_length=1)
    claim_boundary: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def entries_reconcile(self) -> ProductArtifactManifest:
        if self.artifact_count != len(self.artifacts):
            raise ValueError("product artifact count must match entries")
        paths = [item.path for item in self.artifacts]
        if paths != sorted(set(paths)):
            raise ValueError("product artifact paths must be sorted and unique")
        return self


@dataclass(frozen=True)
class ProductBuildResult:
    output_directory: Path
    manifest_path: Path
    checksum_path: Path
    artifact_paths: tuple[Path, ...]


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _model_bytes(document: StrictModel) -> bytes:
    return _json_bytes(document.model_dump(mode="json", exclude_none=True))


def _collection(kind: str, items: Sequence[StrictModel], claim_boundary: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "kind": kind,
        "record_count": len(items),
        "items": [item.model_dump(mode="json", exclude_none=True) for item in items],
        "claim_boundary": claim_boundary,
    }


def _write_json(root: Path, relative: str, payload: object) -> Path:
    path = root / relative
    atomic_write(path, _json_bytes(payload))
    return path


def _write_model(root: Path, relative: str, document: StrictModel) -> Path:
    path = root / relative
    atomic_write(path, _model_bytes(document))
    return path


def _schema_documents() -> dict[str, dict[str, object]]:
    models: tuple[type[StrictModel], ...] = (
        ProductHealth,
        CatalogSummary,
        CitySummary,
        CityPage,
        CityDetail,
        ScenarioSummary,
        ScenarioPage,
        ScenarioDetail,
        ScenarioDesignSummary,
        ScenarioDesignPage,
        ScenarioDesignDetail,
        ScenarioFamilySummary,
        ScenarioFamilyPage,
        ScenarioFamilyDetail,
        ScenarioLibraryEvidence,
        ScenarioDesign,
        ScenarioFamily,
        ScenarioLibraryAudit,
        ScenarioLibraryRegistry,
        SourceSummary,
        SourcePage,
        SuiteOverview,
        BenchmarkOverview,
        PluginManifest,
        PluginPackage,
        PluginPackageSummary,
        ProductArtifactEntry,
        ProductArtifactManifest,
    )
    return {
        "schemas/"
        + re.sub(r"(?<!^)(?=[A-Z])", "-", model.__name__).lower()
        + ".schema.json": model.model_json_schema(mode="validation")
        for model in models
    }


def _web_asset_manifest(repository_root: Path) -> dict[str, object]:
    web_root = repository_root / "src/civicdecision/web"
    relatives = ("index.html", "favicon.svg", "assets/app.css", "assets/app.js")
    assets = []
    for relative in relatives:
        path = web_root / relative
        if not path.is_file():
            raise IntegrityError(f"product web asset is missing: {path}")
        assets.append(
            {
                "path": relative,
                "byte_count": path.stat().st_size,
                "content_hash": sha256_file(path),
            }
        )
    return {
        "schema_version": "1.0.0",
        "asset_count": len(assets),
        "assets": assets,
        "security_boundary": (
            "The packaged explorer has no third-party runtime assets and consumes only the "
            "same-origin read-only API."
        ),
    }


def _build_into(
    repository_root: Path, output: Path
) -> tuple[list[Path], dict[Path, int | None], ArtifactStore]:
    store = ArtifactStore(repository_root, verify_sources=True)
    files: list[Path] = []
    records: dict[Path, int | None] = {}

    def write_model(relative: str, document: StrictModel, count: int | None = None) -> None:
        path = _write_model(output, relative, document)
        files.append(path)
        records[path] = count

    def write_json(relative: str, payload: object, count: int | None = None) -> None:
        path = _write_json(output, relative, payload)
        files.append(path)
        records[path] = count

    write_model("catalog-summary.json", store.summary)
    city_sets = {
        "highest-available": store.highest_tier_city_summaries,
        "tier-g": store.global_city_summaries,
        "tier-s": store.standard_city_summaries,
        "tier-d": store.deep_city_summaries,
    }
    for name, cities in city_sets.items():
        write_json(
            f"cities/{name}.json",
            _collection(
                f"cities.{name}",
                list(cities),
                "Tier labels describe evidence readiness, not deployment or impact.",
            ),
            len(cities),
        )

    scenario_sets = {
        "all": store.all_scenario_summaries,
        "standard-screen": [
            item
            for item in store.all_scenario_summaries
            if item.kind is ScenarioKind.STANDARD_SCREEN
        ],
        "deep-pack": [
            item for item in store.all_scenario_summaries if item.kind is ScenarioKind.DEEP_PACK
        ],
        "reference-pack": [
            item
            for item in store.all_scenario_summaries
            if item.kind is ScenarioKind.REFERENCE_PACK
        ],
        "decision-pack": [
            item
            for item in store.all_scenario_summaries
            if item.kind in {ScenarioKind.DEEP_PACK, ScenarioKind.REFERENCE_PACK}
        ],
    }
    for name, scenarios in scenario_sets.items():
        write_json(
            f"scenarios/{name}.json",
            _collection(
                f"scenarios.{name}",
                list(scenarios),
                "Negative releases and withheld recommendations remain first-class records.",
            ),
            len(scenarios),
        )

    designs = store.scenario_design_summaries
    design_sets: dict[str, Sequence[StrictModel]] = {
        "index": list(designs),
        "reference-implemented": [
            item
            for item in designs
            if item.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
        ],
        "design-only": [
            item
            for item in designs
            if item.implementation_status is ImplementationStatus.DESIGN_ONLY
        ],
    }
    for suite in sorted({item.suite for item in designs}):
        design_sets[f"suite/{suite}"] = [item for item in designs if item.suite == suite]
    for decision_type in DecisionType:
        design_sets[f"decision-type/{decision_type.value}"] = [
            item for item in designs if item.decision_type is decision_type
        ]
    for name, design_rows in sorted(design_sets.items()):
        write_json(
            f"designs/{name}.json",
            _collection(
                f"scenario-designs.{name.replace('/', '.')}",
                design_rows,
                "Design records are not city executions, deployments, adoptions, or impacts.",
            ),
            len(design_rows),
        )
    for design in designs:
        write_model(
            f"designs/detail/{design.design_id}.json",
            store.scenario_design_detail(design.design_id),
            1,
        )

    families = store.scenario_family_summaries
    write_json(
        "design-families/index.json",
        _collection(
            "scenario-design-families",
            families,
            "Each family is a coverage group of eight decision types, not one delivered project.",
        ),
        len(families),
    )
    for family in families:
        write_model(
            f"design-families/detail/{family.family_id}.json",
            store.scenario_family_detail(family.family_id),
            8,
        )

    write_json(
        "sources/index.json",
        _collection(
            "sources",
            store.source_summaries,
            "Source records document public inputs and do not establish outcome validity.",
        ),
        len(store.source_summaries),
    )
    suites = store.suites()
    write_json(
        "suites/index.json",
        _collection(
            "application-suites",
            suites,
            "City bindings are executions of shared designs, not independent methods.",
        ),
        len(suites),
    )
    write_model("benchmarks/overview.json", store.benchmark_overview())
    write_model("evidence/tier-d-summary.json", store.deep_evidence, 96)
    write_model(
        "evidence/scenario-library-summary.json",
        store.scenario_library_evidence(),
        240,
    )
    write_model(
        "evidence/scenario-library-audit.json",
        store.scenario_library_audit,
        240,
    )
    write_model(
        "evidence/scenario-library-registry.json",
        store.scenario_library_registry,
        270,
    )
    write_json("openapi-v1.json", create_app(store=store).openapi())
    write_json("web-assets.json", _web_asset_manifest(repository_root), 4)
    for relative, schema in sorted(_schema_documents().items()):
        write_json(relative, schema)
    return files, records, store


def build_product_artifacts(repository_root: Path, output_directory: Path) -> ProductBuildResult:
    """Build a deterministic, checksum-complete product catalog projection."""

    repository_root = repository_root.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="civicdecision-product-") as temporary:
        staged = Path(temporary) / "product"
        staged.mkdir(parents=True)
        files, records, store = _build_into(repository_root, staged)
        entries = []
        for path in sorted(files):
            relative = path.relative_to(staged).as_posix()
            entries.append(
                ProductArtifactEntry(
                    path=relative,
                    media_type="application/schema+json"
                    if relative.startswith("schemas/")
                    else "application/json",
                    byte_count=path.stat().st_size,
                    content_hash=sha256_file(path),
                    record_count=records[path],
                )
            )
        manifest = ProductArtifactManifest(
            software_version=__version__,
            catalog_fingerprint=store.catalog_fingerprint,
            artifact_count=len(entries),
            artifacts=entries,
            claim_boundary=store.summary.claim_boundary,
        )
        manifest_path = _write_model(staged, "artifact-manifest.json", manifest)
        all_paths = sorted([*files, manifest_path])
        checksums = "".join(
            f"{sha256_file(path)[7:]}  {path.relative_to(staged).as_posix()}\n"
            for path in all_paths
        ).encode("ascii")
        checksum_path = staged / "SHA256SUMS"
        atomic_write(checksum_path, checksums)
        all_paths.append(checksum_path)

        expected = {path.relative_to(staged) for path in all_paths}
        existing = (
            {
                path.relative_to(output_directory)
                for path in output_directory.rglob("*")
                if path.is_file()
            }
            if output_directory.exists()
            else set()
        )
        unexpected = existing - expected
        if unexpected:
            raise IntegrityError(
                "product artifact directory contains unexpected files: "
                + ", ".join(path.as_posix() for path in sorted(unexpected))
            )
        for staged_path in all_paths:
            relative_path = staged_path.relative_to(staged)
            atomic_write(output_directory / relative_path, staged_path.read_bytes())

    artifact_paths = tuple(sorted(path for path in output_directory.rglob("*") if path.is_file()))
    return ProductBuildResult(
        output_directory=output_directory,
        manifest_path=output_directory / "artifact-manifest.json",
        checksum_path=output_directory / "SHA256SUMS",
        artifact_paths=artifact_paths,
    )


__all__ = [
    "ProductArtifactEntry",
    "ProductArtifactManifest",
    "ProductBuildResult",
    "build_product_artifacts",
]
