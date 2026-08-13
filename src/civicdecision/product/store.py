"""Validated read-only repository over committed CivicDecision artifacts."""

from __future__ import annotations

import re
from collections import Counter
from functools import cached_property
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from civicdecision import __version__
from civicdecision.benchmarks.models import BenchmarkEvidenceSummary
from civicdecision.deep.models import (
    ApplicationSuite,
    DeepCityBundle,
    DeepScenarioPack,
    DeepScenarioStatus,
    TierDEvidenceSummary,
    TierDRegistry,
)
from civicdecision.errors import CivicDecisionError, IntegrityError
from civicdecision.product.models import (
    BenchmarkOverview,
    CapabilityView,
    CatalogSummary,
    CityDetail,
    CityPage,
    CitySummary,
    MetricView,
    Pagination,
    ProductTier,
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
    ScenarioStatus,
    ScenarioSummary,
    SourcePage,
    SourceSummary,
    SuiteOverview,
)
from civicdecision.protocols.base import (
    JsonValue,
    StrictModel,
    canonical_json,
    sha256_bytes,
    sha256_file,
)
from civicdecision.protocols.decision import DecisionPack, RunStatus
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.scenario_library.models import (
    CurrentReadiness,
    DecisionType,
    ImplementationStatus,
    ScenarioDesign,
    ScenarioFamily,
    ScenarioLibraryAudit,
    ScenarioLibraryManifest,
    ScenarioLibraryRegistry,
)
from civicdecision.semantic.city_catalog import GlobalCityCatalog, GlobalCityCatalogEntry
from civicdecision.standardized.models import (
    ScenarioScreenStatus,
    StandardizedCityBundle,
    StandardScenarioRun,
    TierSRegistry,
)


class ProductCatalogError(CivicDecisionError):
    """The committed product catalog is unavailable or internally inconsistent."""


class ProductNotFoundError(ProductCatalogError):
    """A requested public artifact does not exist in the registered catalog."""


def _safe_reference(root: Path, reference: str) -> Path:
    candidate = (root / reference).resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise IntegrityError(f"registered product reference escapes its root: {reference}")
    return candidate


def _page(total: int, limit: int, offset: int) -> Pagination:
    returned = min(limit, max(0, total - offset))
    next_offset = offset + returned if offset + returned < total else None
    return Pagination(
        total=total,
        limit=limit,
        offset=offset,
        returned=returned,
        next_offset=next_offset,
    )


def _json_payload(model: StrictModel) -> dict[str, JsonValue]:
    value = model.model_dump(mode="json")
    return cast(dict[str, JsonValue], value)


def _searchable(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


class ArtifactStore:
    """Load validated artifacts and expose conservative, immutable product projections.

    The store accepts one repository root at construction time. API parameters never become file
    paths; all subsequent resolution uses validated registry references or fixed filenames.
    """

    def __init__(self, repository_root: str | Path, *, verify_sources: bool = True) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        if not (self.repository_root / "pyproject.toml").is_file():
            raise ProductCatalogError(
                f"repository root lacks pyproject.toml: {self.repository_root}"
            )
        self.global_root = self.repository_root / "catalog/global-cities"
        self.standard_root = self.repository_root / "catalog/standardized-cities"
        self.deep_root = self.repository_root / "catalog/deep-cities"
        self.scenario_library_root = self.repository_root / "catalog/scenario-library"
        self.benchmark_root = self.repository_root / "benchmarks/milestone-4"
        self.examples_root = self.repository_root / "examples"
        try:
            self.global_catalog = GlobalCityCatalog.model_validate_json(
                (self.global_root / "cities-tier-g.json").read_bytes()
            )
            self.standard_registry = TierSRegistry.model_validate_json(
                (self.standard_root / "registry.json").read_bytes()
            )
            self.deep_registry = TierDRegistry.model_validate_json(
                (self.deep_root / "registry.json").read_bytes()
            )
            self.deep_evidence = TierDEvidenceSummary.model_validate_json(
                (self.deep_root / "evidence-summary.json").read_bytes()
            )
            self.benchmark_evidence = BenchmarkEvidenceSummary.model_validate_json(
                (self.benchmark_root / "evidence-summary.json").read_bytes()
            )
            self.scenario_library_registry = ScenarioLibraryRegistry.model_validate_json(
                (self.scenario_library_root / "registry.json").read_bytes()
            )
            self.scenario_library_audit = ScenarioLibraryAudit.model_validate_json(
                (self.scenario_library_root / "audit.json").read_bytes()
            )
            self.scenario_library_manifest = ScenarioLibraryManifest.model_validate_json(
                (self.scenario_library_root / "artifact-manifest.json").read_bytes()
            )
        except (OSError, ValidationError) as exc:
            raise ProductCatalogError(f"product registry failed validation: {exc}") from exc
        self._validate_registry_files()
        self._validate_scenario_library_files()
        self.source_manifests = self._load_source_manifests(verify_sources=verify_sources)

    def _validate_registry_files(self) -> None:
        for standard_entry in self.standard_registry.entries:
            path = _safe_reference(self.standard_root, standard_entry.bundle_ref)
            if not path.is_file():
                raise IntegrityError(f"Tier-S bundle is missing: {standard_entry.city_id}")
            standard_bundle = StandardizedCityBundle.model_validate_json(path.read_bytes())
            if standard_bundle.content_hash() != standard_entry.bundle_hash:
                raise IntegrityError(f"Tier-S bundle hash mismatch: {standard_entry.city_id}")
        for deep_entry in self.deep_registry.entries:
            path = _safe_reference(self.deep_root, deep_entry.bundle_ref)
            if not path.is_file():
                raise IntegrityError(f"Tier-D bundle is missing: {deep_entry.city_id}")
            deep_bundle = DeepCityBundle.model_validate_json(path.read_bytes())
            if deep_bundle.content_hash() != deep_entry.bundle_hash:
                raise IntegrityError(f"Tier-D bundle hash mismatch: {deep_entry.city_id}")
            if len(deep_entry.scenario_pack_refs) != len(deep_entry.scenario_pack_hashes):
                raise IntegrityError(
                    f"Tier-D scenario registry is misaligned: {deep_entry.city_id}"
                )
            for reference, expected in zip(
                deep_entry.scenario_pack_refs, deep_entry.scenario_pack_hashes, strict=True
            ):
                path = _safe_reference(self.deep_root, reference)
                if not path.is_file():
                    raise IntegrityError(f"Tier-D scenario pack is missing: {reference}")
                pack = DeepScenarioPack.model_validate_json(path.read_bytes())
                if pack.content_hash() != expected:
                    raise IntegrityError(f"Tier-D scenario pack hash mismatch: {reference}")

    def _load_source_manifests(self, *, verify_sources: bool) -> dict[str, SourceManifest]:
        manifests: dict[str, SourceManifest] = {}
        for path in sorted((self.examples_root / "data").glob("**/*.manifest.json")):
            try:
                manifest = SourceManifest.model_validate_json(path.read_bytes())
                if verify_sources:
                    manifest.verify_artifact(path.parent)
            except (OSError, ValidationError, CivicDecisionError) as exc:
                raise ProductCatalogError(
                    f"source manifest failed validation: {path}: {exc}"
                ) from exc
            previous = manifests.get(manifest.artifact_id)
            if previous is not None and canonical_json(previous) != canonical_json(manifest):
                raise IntegrityError(f"source artifact id is ambiguous: {manifest.artifact_id}")
            manifests[manifest.artifact_id] = manifest
        if not manifests:
            raise ProductCatalogError("no source manifests were found")
        return manifests

    def _validate_scenario_library_files(self) -> None:
        manifest_entries = {item.path: item for item in self.scenario_library_manifest.artifacts}
        if len(manifest_entries) != 280:
            raise IntegrityError("scenario library manifest must contain 280 unique base artifacts")
        expected_files = {
            *manifest_entries,
            "artifact-manifest.json",
            "SHA256SUMS",
        }
        actual_files = {
            path.relative_to(self.scenario_library_root).as_posix()
            for path in self.scenario_library_root.rglob("*")
            if path.is_file()
        }
        if actual_files != expected_files:
            missing = sorted(expected_files - actual_files)
            unexpected = sorted(actual_files - expected_files)
            raise IntegrityError(
                f"scenario library file inventory mismatch: missing={missing}, "
                f"unexpected={unexpected}"
            )
        for relative, manifest_entry in manifest_entries.items():
            path = _safe_reference(self.scenario_library_root, relative)
            if (
                not path.is_file()
                or path.stat().st_size != manifest_entry.byte_count
                or sha256_file(path) != manifest_entry.content_hash
            ):
                raise IntegrityError(f"scenario library manifest mismatch: {relative}")
        checksum_lines = (
            (self.scenario_library_root / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        )
        checksum_targets: set[str] = set()
        for line in checksum_lines:
            try:
                digest, relative = line.split("  ", 1)
            except ValueError as exc:
                raise IntegrityError("scenario library checksum line is malformed") from exc
            if (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or relative in checksum_targets
            ):
                raise IntegrityError("scenario library checksum inventory is malformed")
            path = _safe_reference(self.scenario_library_root, relative)
            if not path.is_file() or sha256_file(path) != f"sha256:{digest}":
                raise IntegrityError(f"scenario library checksum mismatch: {relative}")
            checksum_targets.add(relative)
        if checksum_targets != expected_files - {"SHA256SUMS"}:
            raise IntegrityError("scenario library checksum inventory is incomplete")
        if (
            self.scenario_library_manifest.library_content_hash
            != self.scenario_library_registry.artifact_set_hash
            or not self.scenario_library_audit.audit_passed
            or self.scenario_library_registry.city_bound_execution_count != 0
            or self.scenario_library_registry.method_count_claimed != 0
        ):
            raise IntegrityError("scenario library registry, manifest, or audit does not reconcile")

        designs: dict[str, ScenarioDesign] = {}
        for design_entry in self.scenario_library_registry.designs:
            path = _safe_reference(self.scenario_library_root, design_entry.artifact_path)
            try:
                design = ScenarioDesign.model_validate_json(path.read_bytes())
            except (OSError, ValidationError) as exc:
                raise IntegrityError(
                    f"scenario design failed validation: {design_entry.design_id}"
                ) from exc
            if (
                design.design_id != design_entry.design_id
                or design.design_order != design_entry.design_order
                or design.content_hash() != design_entry.content_hash
            ):
                raise IntegrityError(f"scenario design registry mismatch: {design_entry.design_id}")
            designs[design.design_id] = design
        families: dict[str, ScenarioFamily] = {}
        for family_entry in self.scenario_library_registry.families:
            path = _safe_reference(self.scenario_library_root, family_entry.artifact_path)
            try:
                family = ScenarioFamily.model_validate_json(path.read_bytes())
            except (OSError, ValidationError) as exc:
                raise IntegrityError(
                    f"scenario family failed validation: {family_entry.family_id}"
                ) from exc
            if (
                family.family_id != family_entry.family_id
                or family.family_order != family_entry.family_order
                or family.content_hash() != family_entry.content_hash
            ):
                raise IntegrityError(f"scenario family registry mismatch: {family_entry.family_id}")
            if any(
                design_id not in designs or designs[design_id].family_id != family.family_id
                for design_id in family.design_refs
            ):
                raise IntegrityError(
                    f"scenario family design references are invalid: {family_entry.family_id}"
                )
            families[family.family_id] = family
        if len(designs) != 240 or len(families) != 30:
            raise IntegrityError("scenario library validated object counts do not reconcile")
        self._scenario_designs = designs
        self._scenario_families = families

    @cached_property
    def catalog_fingerprint(self) -> str:
        inputs = {
            "global": self.global_catalog.content_hash(),
            "standard": self.standard_registry.content_hash(),
            "deep": self.deep_registry.content_hash(),
            "deep-evidence": sha256_file(self.deep_root / "evidence-summary.json"),
            "benchmarks": self.benchmark_evidence.content_hash(),
            "scenario-library-records": self.scenario_library_registry.artifact_set_hash,
            "scenario-library-audit": sha256_file(self.scenario_library_root / "audit.json"),
            "scenario-library-manifest": sha256_file(
                self.scenario_library_root / "artifact-manifest.json"
            ),
            "reference-completed": sha256_file(
                self.examples_root / "outputs/suffolk-heat-access/decision-pack.json"
            ),
            "reference-infeasible": sha256_file(
                self.examples_root / "outputs/suffolk-heat-access-infeasible/decision-pack.json"
            ),
        }
        return sha256_bytes(canonical_json(inputs))

    @property
    def etag(self) -> str:
        """Return the representation identity for the catalog metadata endpoint."""

        return self.etag_for("/api/v1/meta")

    def etag_for(
        self,
        resource_path: str,
        query_pairs: tuple[tuple[str, str], ...] = (),
    ) -> str:
        """Return a weak ETag scoped to one versioned resource representation.

        A catalog-wide ETag is unsafe for conditional requests because a validator obtained from one
        endpoint could incorrectly suppress a different endpoint. Including software version, path,
        and normalized query pairs also invalidates cached representations after behavior changes
        even when the underlying catalog artifacts have not changed. The validator is weak because
        it identifies the semantic projection rather than hashing final content-encoded HTTP bytes.
        """

        representation_hash = sha256_bytes(
            canonical_json(
                {
                    "catalog_fingerprint": self.catalog_fingerprint,
                    "query_pairs": [list(pair) for pair in query_pairs],
                    "resource_path": resource_path,
                    "software_version": __version__,
                }
            )
        )
        return f'W/"{representation_hash[7:]}"'

    @cached_property
    def global_by_id(self) -> dict[str, GlobalCityCatalogEntry]:
        return {item.city_id: item for item in self.global_catalog.cities}

    @cached_property
    def standard_entries(self) -> dict[str, object]:
        return {item.city_id: item for item in self.standard_registry.entries}

    @cached_property
    def deep_entries(self) -> dict[str, object]:
        return {item.city_id: item for item in self.deep_registry.entries}

    @cached_property
    def scenario_design_summaries(self) -> list[ScenarioDesignSummary]:
        summaries = []
        for design in sorted(self._scenario_designs.values(), key=lambda item: item.design_order):
            primary = next(item for item in design.objectives if item.primary)
            binding = next(item for item in design.constraints if item.binding)
            summaries.append(
                ScenarioDesignSummary(
                    design_order=design.design_order,
                    design_id=design.design_id,
                    family_id=design.family_id,
                    suite=design.suite.value,
                    family_title=design.family_title,
                    title=design.title,
                    decision_question=design.decision_question,
                    decision_type=design.decision_type,
                    horizon=design.horizon,
                    spatial_unit=design.spatial_unit,
                    primary_outcome=primary.metric,
                    binding_constraint=binding.description,
                    evidence_gate=design.release_gate.gate_type,
                    implementation_status=design.implementation_status,
                    current_readiness=design.current_readiness,
                    existing_template_ref=design.existing_template_ref,
                    analysis_modes=[item.value for item in design.analysis_modes],
                    evidence_types=design.evidence_requirements,
                    prohibited_claims=design.prohibited_claims,
                    content_hash=design.content_hash(),
                )
            )
        return summaries

    @cached_property
    def scenario_family_summaries(self) -> list[ScenarioFamilySummary]:
        summaries = []
        for family in sorted(self._scenario_families.values(), key=lambda item: item.family_order):
            designs = [self._scenario_designs[design_id] for design_id in family.design_refs]
            implemented = sum(
                item.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
                for item in designs
            )
            summaries.append(
                ScenarioFamilySummary(
                    family_order=family.family_order,
                    family_id=family.family_id,
                    suite=family.suite.value,
                    title=family.title,
                    description=family.description,
                    affected_system=family.affected_system,
                    decision_owner=family.decision_owner,
                    design_count=len(designs),
                    reference_implemented_count=implemented,
                    design_only_count=len(designs) - implemented,
                    decision_types=family.decision_types,
                    content_hash=family.content_hash(),
                )
            )
        return summaries

    def list_scenario_designs(
        self,
        *,
        suite: ApplicationSuite | None = None,
        family_id: str | None = None,
        decision_type: DecisionType | None = None,
        implementation_status: ImplementationStatus | None = None,
        current_readiness: CurrentReadiness | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioDesignPage:
        rows = self.scenario_design_summaries
        if suite is not None:
            rows = [item for item in rows if item.suite == suite.value]
        if family_id is not None:
            rows = [item for item in rows if item.family_id == family_id]
        if decision_type is not None:
            rows = [item for item in rows if item.decision_type is decision_type]
        if implementation_status is not None:
            rows = [item for item in rows if item.implementation_status is implementation_status]
        if current_readiness is not None:
            rows = [item for item in rows if item.current_readiness is current_readiness]
        if query is not None:
            needle = _searchable(query)
            rows = [
                item
                for item in rows
                if needle
                in _searchable(
                    " ".join(
                        (
                            item.design_id,
                            item.family_id,
                            item.family_title,
                            item.title,
                            item.decision_question,
                            item.primary_outcome,
                            item.binding_constraint,
                        )
                    )
                )
            ]
        pagination = _page(len(rows), limit, offset)
        return ScenarioDesignPage(
            pagination=pagination,
            items=rows[offset : offset + pagination.returned],
        )

    def scenario_design_detail(self, design_id: str) -> ScenarioDesignDetail:
        design = self._scenario_designs.get(design_id)
        if design is None:
            raise ProductNotFoundError(f"unknown scenario design: {design_id}")
        return ScenarioDesignDetail(
            design=design,
            family=self._scenario_families[design.family_id],
            library_claim_boundary=self.scenario_library_registry.claim_boundary,
            audit_maximum_pairwise_similarity=(
                self.scenario_library_audit.maximum_pairwise_similarity
            ),
        )

    def list_scenario_families(
        self,
        *,
        suite: ApplicationSuite | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioFamilyPage:
        rows = self.scenario_family_summaries
        if suite is not None:
            rows = [item for item in rows if item.suite == suite.value]
        if query is not None:
            needle = _searchable(query)
            rows = [
                item
                for item in rows
                if needle
                in _searchable(
                    " ".join(
                        (
                            item.family_id,
                            item.title,
                            item.description,
                            item.affected_system,
                            item.decision_owner,
                        )
                    )
                )
            ]
        pagination = _page(len(rows), limit, offset)
        return ScenarioFamilyPage(
            pagination=pagination,
            items=rows[offset : offset + pagination.returned],
        )

    def scenario_family_detail(self, family_id: str) -> ScenarioFamilyDetail:
        family = self._scenario_families.get(family_id)
        if family is None:
            raise ProductNotFoundError(f"unknown scenario family: {family_id}")
        by_id = {item.design_id: item for item in self.scenario_design_summaries}
        return ScenarioFamilyDetail(
            family=family,
            designs=[by_id[design_id] for design_id in family.design_refs],
            library_claim_boundary=self.scenario_library_registry.claim_boundary,
        )

    def scenario_library_evidence(self) -> ScenarioLibraryEvidence:
        registry = self.scenario_library_registry
        audit = self.scenario_library_audit
        manifest = self.scenario_library_manifest
        return ScenarioLibraryEvidence(
            design_count=registry.design_count,
            family_count=registry.family_count,
            reference_implemented_designs=registry.implementation_status_counts[
                ImplementationStatus.REFERENCE_IMPLEMENTED
            ],
            design_only_scenarios=registry.implementation_status_counts[
                ImplementationStatus.DESIGN_ONLY
            ],
            city_bound_executions_counted=registry.city_bound_execution_count,
            methods_claimed=registry.method_count_claimed,
            audit_passed=audit.audit_passed,
            high_similarity_threshold=audit.high_similarity_threshold,
            maximum_pairwise_similarity=audit.maximum_pairwise_similarity,
            high_similarity_pair_count=len(audit.high_similarity_pairs),
            exact_signature_collision_count=len(audit.exact_signature_collisions),
            duplicate_title_count=len(audit.duplicate_titles),
            duplicate_question_count=len(audit.duplicate_questions),
            artifact_set_hash=registry.artifact_set_hash,
            library_content_hash=manifest.library_content_hash,
            claim_boundary=registry.claim_boundary,
            invariants=audit.invariants,
            limitations=audit.limitations,
        )

    def _standard_bundle(self, city_id: str) -> StandardizedCityBundle:
        entry = next(
            (item for item in self.standard_registry.entries if item.city_id == city_id), None
        )
        if entry is None:
            raise ProductNotFoundError(f"unknown Tier-S city: {city_id}")
        path = _safe_reference(self.standard_root, entry.bundle_ref)
        bundle = StandardizedCityBundle.model_validate_json(path.read_bytes())
        if bundle.content_hash() != entry.bundle_hash:
            raise IntegrityError(f"Tier-S bundle changed after store initialization: {city_id}")
        return bundle

    def _deep_bundle(self, city_id: str) -> DeepCityBundle:
        entry = next((item for item in self.deep_registry.entries if item.city_id == city_id), None)
        if entry is None:
            raise ProductNotFoundError(f"unknown Tier-D city: {city_id}")
        path = _safe_reference(self.deep_root, entry.bundle_ref)
        bundle = DeepCityBundle.model_validate_json(path.read_bytes())
        if bundle.content_hash() != entry.bundle_hash:
            raise IntegrityError(f"Tier-D bundle changed after store initialization: {city_id}")
        return bundle

    @cached_property
    def global_city_summaries(self) -> list[CitySummary]:
        return [
            CitySummary(
                city_id=item.city_id,
                name=item.name,
                country_code=item.country_code,
                tier=ProductTier.GLOBAL,
                latitude=item.location.latitude,
                longitude=item.location.longitude,
                timezone=item.timezone,
                source_population=item.source_population,
                source_artifact_count=1,
                scenario_count=0,
                completed_scenarios=0,
                negative_scenarios=0,
                readiness="catalog-discovery-only",
                limitations=item.limitations,
            )
            for item in self.global_catalog.cities
        ]

    @cached_property
    def standard_city_summaries(self) -> list[CitySummary]:
        values: list[CitySummary] = []
        for entry in self.standard_registry.entries:
            global_entry = self.global_by_id[entry.city_id]
            completed = sum(
                item is ScenarioScreenStatus.SCREENED for item in entry.scenario_statuses
            )
            values.append(
                CitySummary(
                    city_id=entry.city_id,
                    name=entry.name,
                    country_code=entry.country_code,
                    tier=ProductTier.STANDARDIZED,
                    latitude=global_entry.location.latitude,
                    longitude=global_entry.location.longitude,
                    timezone=global_entry.timezone,
                    source_population=global_entry.source_population,
                    quality_status=entry.quality_status.value,
                    source_artifact_count=5,
                    scenario_count=len(entry.scenario_statuses),
                    completed_scenarios=completed,
                    negative_scenarios=len(entry.scenario_statuses) - completed,
                    readiness="standardized-descriptive-screening",
                    limitations=[
                        "Tier-S outputs are descriptive screens and cannot issue recommendations.",
                        "Country indicators remain national context and climate remains one "
                        "grid point.",
                    ],
                )
            )
        return values

    @cached_property
    def deep_city_summaries(self) -> list[CitySummary]:
        values: list[CitySummary] = []
        for entry in self.deep_registry.entries:
            bundle = self._deep_bundle(entry.city_id)
            bbox = bundle.adapter.bbox
            population = next(
                (
                    int(item.value)
                    for item in bundle.metrics
                    if item.id == "demography.population-estimate"
                    and isinstance(item.value, int | float)
                ),
                None,
            )
            values.append(
                CitySummary(
                    city_id=entry.city_id,
                    name=entry.display_name,
                    country_code=bundle.adapter.country_code,
                    tier=ProductTier.DEEP,
                    latitude=(bbox.south + bbox.north) / 2,
                    longitude=(bbox.west + bbox.east) / 2,
                    timezone=bundle.adapter.timezone,
                    source_population=population,
                    quality_status=entry.quality_status.value,
                    source_artifact_count=len(bundle.source_manifests),
                    scenario_count=len(entry.scenario_pack_refs),
                    completed_scenarios=entry.completed_scenarios,
                    negative_scenarios=entry.negative_scenarios,
                    readiness="evidence-gated-planning-support",
                    limitations=bundle.limitations,
                )
            )
        return values

    @cached_property
    def highest_tier_city_summaries(self) -> list[CitySummary]:
        records = {item.city_id: item for item in self.global_city_summaries}
        records.update({item.city_id: item for item in self.standard_city_summaries})
        records.update({item.city_id: item for item in self.deep_city_summaries})
        return sorted(records.values(), key=lambda item: (item.name.casefold(), item.city_id))

    def list_cities(
        self,
        *,
        tier: ProductTier | None = None,
        query: str | None = None,
        country_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CityPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("city pagination requires limit 1..100 and nonnegative offset")
        if tier is ProductTier.GLOBAL:
            values = list(self.global_city_summaries)
        elif tier is ProductTier.STANDARDIZED:
            values = list(self.standard_city_summaries)
        elif tier is ProductTier.DEEP:
            values = list(self.deep_city_summaries)
        else:
            values = list(self.highest_tier_city_summaries)
        if query:
            needle = query.casefold().strip()
            values = [
                item
                for item in values
                if needle in item.name.casefold()
                or needle in item.city_id.casefold()
                or needle in item.country_code.casefold()
            ]
        if country_code:
            normalized_country = country_code.upper()
            values = [item for item in values if item.country_code == normalized_country]
        if tier is not None:
            values.sort(key=lambda item: (item.name.casefold(), item.city_id))
        page = _page(len(values), limit, offset)
        return CityPage(pagination=page, items=values[offset : offset + limit])

    def city_detail(self, city_id: str) -> CityDetail:
        if any(item.city_id == city_id for item in self.deep_city_summaries):
            return self._deep_city_detail(city_id)
        if any(item.city_id == city_id for item in self.standard_city_summaries):
            return self._standard_city_detail(city_id)
        if city_id in self.global_by_id:
            return self._global_city_detail(city_id)
        raise ProductNotFoundError(f"unknown city: {city_id}")

    def _global_city_detail(self, city_id: str) -> CityDetail:
        entry = self.global_by_id[city_id]
        summary = next(item for item in self.global_city_summaries if item.city_id == city_id)
        return CityDetail(
            city=summary,
            source_ids=[self.global_catalog.source_manifest.source_id],
            source_artifact_ids=[self.global_catalog.source_manifest.artifact_id],
            metrics=[
                MetricView(
                    id="catalog.source-population",
                    value=entry.source_population,
                    unit="people as published by GeoNames",
                    evidence_type=EvidenceType.OBSERVED,
                    method=(
                        "Retain the source population field without harmonizing its reference year."
                    ),
                    source_refs=[entry.source_ref],
                    interpretation=(
                        "A catalog ordering field, not a comparable current population estimate."
                    ),
                    limitations=entry.limitations,
                )
            ],
            capabilities=[
                CapabilityView(
                    id="catalog.discovery",
                    status="ready",
                    diagnostics=["A versioned point identity is present in the Tier-G catalog."],
                    evidence_refs=[entry.source_ref],
                    limitations=["Discovery does not imply local analytical readiness."],
                )
            ],
            quality_checks={},
            data_gaps=["Official local boundary and intervention evidence are not part of Tier G."],
            provenance={
                "selection_rank": entry.selection_rank,
                "selection_basis": entry.selection_basis,
                "source_modification_date": entry.source_modification_date.isoformat(),
                "catalog_content_hash": self.global_catalog.content_hash(),
            },
            limitations=entry.limitations,
        )

    def _standard_city_detail(self, city_id: str) -> CityDetail:
        bundle = self._standard_bundle(city_id)
        summary = next(item for item in self.standard_city_summaries if item.city_id == city_id)
        metrics = [
            MetricView(
                id=item.id,
                value=item.value,
                unit=item.unit,
                evidence_type=item.evidence_type,
                method=item.method or "Direct projection of a validated standardized metric.",
                source_refs=item.source_refs,
                interpretation=f"{item.geographic_scope}; {item.temporal_scope}.",
                limitations=item.limitations,
            )
            for item in bundle.metrics
        ]
        capabilities = [
            CapabilityView(
                id="standardized.descriptive-screening",
                status="ready",
                diagnostics=[
                    "All required Tier-S identity, gridded-point, and country-context layers "
                    "passed."
                ],
                evidence_refs=sorted(item.artifact_id for item in bundle.source_manifests),
                limitations=["This capability cannot issue an intervention recommendation."],
            )
        ]
        return CityDetail(
            city=summary,
            source_ids=sorted({item.source_id for item in bundle.source_manifests}),
            source_artifact_ids=sorted(item.artifact_id for item in bundle.source_manifests),
            metrics=metrics,
            capabilities=capabilities,
            quality_checks={item.id: item.status.value for item in bundle.quality_report.checks},
            data_gaps=bundle.adapter.data_gaps,
            provenance={
                "bundle_id": bundle.bundle_id,
                "bundle_content_hash": bundle.content_hash(),
                "catalog_rank": bundle.catalog_entry.selection_rank,
            },
            limitations=bundle.limitations,
        )

    def _deep_city_detail(self, city_id: str) -> CityDetail:
        bundle = self._deep_bundle(city_id)
        summary = next(item for item in self.deep_city_summaries if item.city_id == city_id)
        metrics = [
            MetricView(
                id=item.id,
                value=item.value,
                unit=item.unit,
                evidence_type=item.evidence_type,
                method=item.method,
                source_refs=item.source_refs,
                interpretation=item.interpretation,
                limitations=item.limitations,
            )
            for item in bundle.metrics
        ]
        capabilities = [
            CapabilityView(
                id=item.capability_id,
                status=item.status.value,
                diagnostics=item.diagnostics,
                evidence_refs=item.evidence_refs,
                limitations=item.limitations,
            )
            for item in bundle.capabilities
        ]
        return CityDetail(
            city=summary,
            source_ids=sorted({item.source_id for item in bundle.source_manifests}),
            source_artifact_ids=sorted(item.artifact_id for item in bundle.source_manifests),
            metrics=metrics,
            capabilities=capabilities,
            quality_checks={item.id: item.status.value for item in bundle.quality_report.checks},
            data_gaps=bundle.adapter.data_gaps,
            provenance={
                "bundle_id": bundle.bundle_id,
                "bundle_content_hash": bundle.content_hash(),
                "reference_period_start": bundle.reference_period_start.isoformat(),
                "reference_period_end_exclusive": bundle.reference_period_end_exclusive.isoformat(),
            },
            limitations=bundle.limitations,
        )

    @cached_property
    def standard_scenarios(self) -> dict[str, tuple[ScenarioSummary, StandardScenarioRun]]:
        values: dict[str, tuple[ScenarioSummary, StandardScenarioRun]] = {}
        city_names = {item.city_id: item.name for item in self.standard_registry.entries}
        for entry in self.standard_registry.entries:
            for reference, expected_hash in zip(entry.run_refs, entry.run_hashes, strict=True):
                path = _safe_reference(self.standard_root, reference)
                run = StandardScenarioRun.model_validate_json(path.read_bytes())
                if run.content_hash() != expected_hash:
                    raise IntegrityError(f"Tier-S run hash mismatch: {reference}")
                summary = ScenarioSummary(
                    execution_id=run.run_id,
                    scenario_id=run.scenario_id,
                    template_id=run.template_id,
                    kind=ScenarioKind.STANDARD_SCREEN,
                    city_id=run.city_id,
                    city_name=city_names[run.city_id],
                    suite="standardized-screening",
                    title=run.title,
                    status=ScenarioStatus(run.status.value),
                    readiness=run.decision_readiness.value,
                    recommendation_issued=False,
                    observed_request_count=None,
                    source_count=len(run.source_refs),
                    artifact_count=1,
                    analysis_modes=[run.analysis_mode],
                    evidence_types=sorted(
                        {item.evidence_type for item in run.metrics}, key=lambda item: item.value
                    ),
                    content_hash=run.content_hash(),
                    limitations=run.limitations,
                )
                values[summary.execution_id] = (summary, run)
        return values

    @cached_property
    def deep_scenarios(self) -> dict[str, tuple[ScenarioSummary, DeepScenarioPack]]:
        values: dict[str, tuple[ScenarioSummary, DeepScenarioPack]] = {}
        names = {item.city_id: item.display_name for item in self.deep_registry.entries}
        templates = {item.template_id: item for item in self.deep_registry.scenario_templates}
        for entry in self.deep_registry.entries:
            for reference, expected_hash in zip(
                entry.scenario_pack_refs, entry.scenario_pack_hashes, strict=True
            ):
                path = _safe_reference(self.deep_root, reference)
                pack = DeepScenarioPack.model_validate_json(path.read_bytes())
                if pack.content_hash() != expected_hash:
                    raise IntegrityError(f"Tier-D pack hash mismatch: {reference}")
                template = templates[pack.scenario_template_id]
                evidence_types = sorted(
                    {item.type for item in pack.decision_pack.evidence},
                    key=lambda item: item.value,
                )
                selected = pack.decision_pack.recommendation.selected_option_id
                summary = ScenarioSummary(
                    execution_id=pack.pack_id,
                    scenario_id=pack.scenario.scenario_id,
                    template_id=pack.scenario_template_id,
                    kind=ScenarioKind.DEEP_PACK,
                    city_id=pack.city_id,
                    city_name=names[pack.city_id],
                    suite=pack.suite.value,
                    title=template.title,
                    status=ScenarioStatus(pack.status.value),
                    readiness=pack.readiness.value,
                    recommendation_issued=selected is not None,
                    selected_option_id=selected,
                    observed_request_count=pack.observed_request_count,
                    source_count=len(pack.source_refs),
                    artifact_count=len(pack.analytical_artifacts),
                    analysis_modes=[item.value for item in pack.scenario.analysis_modes],
                    evidence_types=evidence_types,
                    content_hash=pack.content_hash(),
                    limitations=pack.limitations,
                )
                values[summary.execution_id] = (summary, pack)
        return values

    @cached_property
    def reference_scenarios(self) -> dict[str, tuple[ScenarioSummary, DecisionPack]]:
        values: dict[str, tuple[ScenarioSummary, DecisionPack]] = {}
        for directory in ("suffolk-heat-access", "suffolk-heat-access-infeasible"):
            path = self.examples_root / "outputs" / directory / "decision-pack.json"
            pack = DecisionPack.model_validate_json(path.read_bytes())
            selected = pack.recommendation.selected_option_id
            summary = ScenarioSummary(
                execution_id=pack.run_id,
                scenario_id=pack.scenario_id,
                kind=ScenarioKind.REFERENCE_PACK,
                city_id="us.ma.suffolk",
                city_name="Suffolk County reference sample",
                suite="heat-access-reference",
                title=(
                    "Completed heat-access reference"
                    if pack.status is RunStatus.COMPLETED
                    else "Deliberately infeasible heat-access reference"
                ),
                status=ScenarioStatus(pack.status.value),
                readiness=(
                    "reference-planning-support"
                    if pack.status is RunStatus.COMPLETED
                    else "negative-release"
                ),
                recommendation_issued=selected is not None,
                selected_option_id=selected,
                source_count=len(pack.source_manifests),
                artifact_count=2,
                analysis_modes=["spatial", "optimization", "sensitivity"],
                evidence_types=sorted(
                    {item.type for item in pack.evidence}, key=lambda item: item.value
                ),
                content_hash=pack.content_hash(),
                limitations=[
                    "This bounded public-data example is implementation evidence, not a "
                    "municipal recommendation."
                ],
            )
            values[summary.execution_id] = (summary, pack)
        return values

    @cached_property
    def all_scenario_summaries(self) -> list[ScenarioSummary]:
        values = [
            *(item[0] for item in self.standard_scenarios.values()),
            *(item[0] for item in self.deep_scenarios.values()),
            *(item[0] for item in self.reference_scenarios.values()),
        ]
        return sorted(values, key=lambda item: (item.city_name.casefold(), item.execution_id))

    def list_scenarios(
        self,
        *,
        kind: ScenarioKind | None = None,
        city_id: str | None = None,
        suite: str | None = None,
        status: ScenarioStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("scenario pagination requires limit 1..100 and nonnegative offset")
        values = list(self.all_scenario_summaries)
        if kind is not None:
            values = [item for item in values if item.kind is kind]
        if city_id:
            values = [item for item in values if item.city_id == city_id]
        if suite:
            values = [item for item in values if item.suite == suite]
        if status:
            values = [item for item in values if item.status == status]
        if query:
            needle = query.casefold().strip()
            values = [
                item
                for item in values
                if needle in item.title.casefold()
                or needle in item.execution_id.casefold()
                or needle in item.city_name.casefold()
                or needle in item.suite.casefold()
            ]
        page = _page(len(values), limit, offset)
        return ScenarioPage(pagination=page, items=values[offset : offset + limit])

    def list_decision_packs(
        self,
        *,
        city_id: str | None = None,
        status: ScenarioStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("DecisionPack pagination requires limit 1..100 and nonnegative offset")
        values = [
            item
            for item in self.all_scenario_summaries
            if item.kind in {ScenarioKind.DEEP_PACK, ScenarioKind.REFERENCE_PACK}
        ]
        if city_id:
            values = [item for item in values if item.city_id == city_id]
        if status:
            values = [item for item in values if item.status == status]
        if query:
            needle = query.casefold().strip()
            values = [
                item
                for item in values
                if needle in item.title.casefold()
                or needle in item.execution_id.casefold()
                or needle in item.city_name.casefold()
            ]
        page = _page(len(values), limit, offset)
        return ScenarioPage(pagination=page, items=values[offset : offset + limit])

    @cached_property
    def source_summaries(self) -> list[SourceSummary]:
        return sorted(
            [
                SourceSummary(
                    artifact_id=item.artifact_id,
                    source_id=item.source_id,
                    name=item.name,
                    publisher=item.publisher,
                    license=item.license,
                    retrieved_at=item.retrieved_at,
                    record_count=item.record_count,
                    geographic_scope=item.geographic_scope,
                    temporal_scope=item.temporal_scope,
                    content_hash=item.content_hash,
                    limitations=item.limitations,
                )
                for item in self.source_manifests.values()
            ],
            key=lambda item: (item.source_id, item.artifact_id),
        )

    def list_sources(
        self,
        *,
        source_id: str | None = None,
        publisher: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SourcePage:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("source pagination requires limit 1..100 and nonnegative offset")
        values = list(self.source_summaries)
        if source_id:
            values = [item for item in values if item.source_id == source_id]
        if publisher:
            needle = publisher.casefold().strip()
            values = [item for item in values if needle in item.publisher.casefold()]
        if query:
            needle = query.casefold().strip()
            values = [
                item
                for item in values
                if needle in item.name.casefold()
                or needle in item.source_id.casefold()
                or needle in item.artifact_id.casefold()
                or needle in item.publisher.casefold()
            ]
        page = _page(len(values), limit, offset)
        return SourcePage(pagination=page, items=values[offset : offset + limit])

    def scenario_detail(self, execution_id: str) -> ScenarioDetail:
        if execution_id in self.deep_scenarios:
            summary, deep_pack = self.deep_scenarios[execution_id]
            return ScenarioDetail(
                scenario=summary,
                payload_schema="deep-scenario-pack.schema.json",
                payload=_json_payload(deep_pack),
                artifact_hashes={
                    item.kind: item.content_hash for item in deep_pack.analytical_artifacts
                },
                claim_boundary=[
                    "Completed means the internal planning-support pipeline ran under declared "
                    "assumptions.",
                    "It does not establish causal impact, operational feasibility, deployment, "
                    "adoption, or real-world outcomes.",
                ],
            )
        if execution_id in self.standard_scenarios:
            summary, run = self.standard_scenarios[execution_id]
            return ScenarioDetail(
                scenario=summary,
                payload_schema="standard-scenario-run.schema.json",
                payload=_json_payload(run),
                artifact_hashes={},
                claim_boundary=[
                    "Tier-S records are descriptive screens only.",
                    "No recommendation, causal result, forecast, simulation, or optimization is "
                    "issued.",
                ],
            )
        if execution_id in self.reference_scenarios:
            summary, reference_pack = self.reference_scenarios[execution_id]
            return ScenarioDetail(
                scenario=summary,
                payload_schema="decision-pack.schema.json",
                payload=_json_payload(reference_pack),
                artifact_hashes={"decision-pack": reference_pack.content_hash()},
                claim_boundary=[
                    "The reference workflow proves bounded implementation behavior only.",
                    "Tract centroids, straight-line distance, and modeled options are not "
                    "observed service outcomes.",
                ],
            )
        raise ProductNotFoundError(f"unknown scenario execution: {execution_id}")

    def decision_pack(self, execution_id: str) -> DecisionPack:
        if execution_id in self.deep_scenarios:
            return self.deep_scenarios[execution_id][1].decision_pack
        if execution_id in self.reference_scenarios:
            return self.reference_scenarios[execution_id][1]
        if execution_id in self.standard_scenarios:
            raise ProductNotFoundError(
                f"standardized screen is deliberately not a DecisionPack: {execution_id}"
            )
        raise ProductNotFoundError(f"unknown DecisionPack: {execution_id}")

    def decision_brief(self, execution_id: str) -> str:
        if execution_id in self.deep_scenarios:
            _, pack = self.deep_scenarios[execution_id]
            reference = next(
                item.path for item in pack.analytical_artifacts if item.kind == "decision-brief"
            )
            return _safe_reference(self.deep_root, reference).read_text(encoding="utf-8")
        if execution_id in self.reference_scenarios:
            for directory in ("suffolk-heat-access", "suffolk-heat-access-infeasible"):
                pack_path = self.examples_root / "outputs" / directory / "decision-pack.json"
                candidate_pack = DecisionPack.model_validate_json(pack_path.read_bytes())
                if candidate_pack.run_id == execution_id:
                    return (pack_path.parent / "decision-brief.md").read_text(encoding="utf-8")
        raise ProductNotFoundError(f"unknown decision brief: {execution_id}")

    def suites(self) -> list[SuiteOverview]:
        deep = [item[0] for item in self.deep_scenarios.values()]
        template_counts = Counter(
            item.suite.value for item in self.deep_registry.scenario_templates
        )
        results: list[SuiteOverview] = []
        for suite in ApplicationSuite:
            rows = [item for item in deep if item.suite == suite.value]
            design_rows = [
                item for item in self.scenario_design_summaries if item.suite == suite.value
            ]
            design_families = {item.family_id for item in design_rows}
            reference_implemented = sum(
                item.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
                for item in design_rows
            )
            completed = sum(item.status == DeepScenarioStatus.COMPLETED.value for item in rows)
            results.append(
                SuiteOverview(
                    suite=suite.value,
                    design_family_count=len(design_families),
                    design_count=len(design_rows),
                    reference_implemented_designs=reference_implemented,
                    design_only_scenarios=len(design_rows) - reference_implemented,
                    template_count=template_counts[suite.value],
                    execution_count=len(rows),
                    completed_count=completed,
                    negative_count=len(rows) - completed,
                    cities=len({item.city_id for item in rows}),
                    claim_boundary=(
                        "Counts are city bindings of shared templates; they are not independent "
                        "methods, field studies, deployments, or observed impacts."
                    ),
                )
            )
        return results

    def benchmark_overview(self) -> BenchmarkOverview:
        evidence = self.benchmark_evidence
        return BenchmarkOverview(
            summary_id=evidence.summary_id,
            artifact_set_hash=evidence.artifact_set_hash,
            run_artifacts=len(evidence.run_artifact_hashes),
            historical_replays=len(evidence.historical_replays),
            replay_training_values=sum(
                item.training_observations for item in evidence.historical_replays
            ),
            replay_holdout_values=sum(
                item.holdout_observations for item in evidence.historical_replays
            ),
            optimization_tasks=len(evidence.optimization_tasks),
            optimization_search_space=evidence.total_search_space_size,
            optimization_evaluated_plans=evidence.total_evaluated_plans,
            optimization_feasible_plans=evidence.total_feasible_plans,
            engine_qualification_runs=len(evidence.engine_qualification_runs),
            status_counts=evidence.optimization_status_counts,
            method_counts=evidence.method_counts,
            limitations=evidence.limitations,
        )

    @cached_property
    def summary(self) -> CatalogSummary:
        completed_reference = sum(
            item[1].status is RunStatus.COMPLETED for item in self.reference_scenarios.values()
        )
        decision_pack_count = self.deep_registry.total_scenario_packs + len(
            self.reference_scenarios
        )
        completed_packs = self.deep_evidence.completed_scenarios + completed_reference
        latest_source = max(item.retrieved_at for item in self.source_manifests.values())
        reference_implemented = self.scenario_library_registry.implementation_status_counts[
            ImplementationStatus.REFERENCE_IMPLEMENTED
        ]
        design_only = self.scenario_library_registry.implementation_status_counts[
            ImplementationStatus.DESIGN_ONLY
        ]
        return CatalogSummary(
            software_version=__version__,
            catalog_fingerprint=self.catalog_fingerprint,
            generated_from_latest_source_at=latest_source,
            tier_g_cities=len(self.global_catalog.cities),
            tier_s_cities=len(self.standard_registry.entries),
            tier_d_cities=len(self.deep_registry.entries),
            exposed_city_records=len(self.highest_tier_city_summaries),
            tier_assignments=(
                len(self.global_catalog.cities)
                + len(self.standard_registry.entries)
                + len(self.deep_registry.entries)
            ),
            source_artifacts=len(self.source_manifests),
            declared_source_units=sum(item.record_count for item in self.source_manifests.values()),
            standard_scenario_screens=len(self.standard_scenarios),
            scenario_library_designs=self.scenario_library_registry.design_count,
            scenario_library_families=self.scenario_library_registry.family_count,
            reference_implemented_designs=reference_implemented,
            design_only_scenarios=design_only,
            scenario_library_city_bindings=(
                self.scenario_library_registry.city_bound_execution_count
            ),
            scenario_library_methods_claimed=self.scenario_library_registry.method_count_claimed,
            scenario_library_audit_passed=self.scenario_library_audit.audit_passed,
            scenario_library_maximum_similarity=(
                self.scenario_library_audit.maximum_pairwise_similarity
            ),
            nonduplicative_deep_designs=self.deep_evidence.nonduplicative_scenario_designs,
            deep_scenario_executions=self.deep_evidence.city_bound_scenario_executions,
            completed_deep_executions=self.deep_evidence.completed_scenarios,
            negative_deep_executions=self.deep_evidence.negative_scenarios,
            decision_packs=decision_pack_count,
            completed_decision_packs=completed_packs,
            negative_decision_packs=decision_pack_count - completed_packs,
            benchmark_run_artifacts=len(self.benchmark_evidence.run_artifact_hashes),
            historical_replays=len(self.benchmark_evidence.historical_replays),
            optimization_benchmarks=len(self.benchmark_evidence.optimization_tasks),
            claim_boundary=[
                "Public data and deterministic software runs are not client work or field "
                "deployment.",
                "Simulation and optimization are not observed impact or institutional adoption.",
                "Repeated city bindings are not counted as independent scenario designs.",
                "The 240-record scenario library counts designs, including 228 design-only "
                "records; it is not a count of city executions or delivered projects.",
                "Negative and insufficient-evidence releases remain visible and selectable.",
            ],
        )


__all__ = ["ArtifactStore", "ProductCatalogError", "ProductNotFoundError"]
