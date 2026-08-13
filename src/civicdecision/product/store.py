"""Validated read-only repository over committed CivicDecision artifacts."""

from __future__ import annotations

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
    ScenarioDetail,
    ScenarioKind,
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
        except (OSError, ValidationError) as exc:
            raise ProductCatalogError(f"product registry failed validation: {exc}") from exc
        self._validate_registry_files()
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

    @cached_property
    def catalog_fingerprint(self) -> str:
        inputs = {
            "global": self.global_catalog.content_hash(),
            "standard": self.standard_registry.content_hash(),
            "deep": self.deep_registry.content_hash(),
            "deep-evidence": sha256_file(self.deep_root / "evidence-summary.json"),
            "benchmarks": self.benchmark_evidence.content_hash(),
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
        return f'"{self.catalog_fingerprint[7:]}"'

    @cached_property
    def global_by_id(self) -> dict[str, GlobalCityCatalogEntry]:
        return {item.city_id: item for item in self.global_catalog.cities}

    @cached_property
    def standard_entries(self) -> dict[str, object]:
        return {item.city_id: item for item in self.standard_registry.entries}

    @cached_property
    def deep_entries(self) -> dict[str, object]:
        return {item.city_id: item for item in self.deep_registry.entries}

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
            completed = sum(item.status == DeepScenarioStatus.COMPLETED.value for item in rows)
            results.append(
                SuiteOverview(
                    suite=suite.value,
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
                "Negative and insufficient-evidence releases remain visible and selectable.",
            ],
        )


__all__ = ["ArtifactStore", "ProductCatalogError", "ProductNotFoundError"]
