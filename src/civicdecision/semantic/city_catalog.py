"""Deterministic Tier-G city catalog and seed graph built from GeoNames."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from civicdecision.connectors.base import atomic_write
from civicdecision.connectors.geonames import (
    GEONAMES_COLUMNS,
    GeoNamesCitiesQuery,
    validate_geonames_zip,
)
from civicdecision.errors import AnalysisError
from civicdecision.io import validate_document
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
    sha256_file,
)
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.semantic.core import Coordinate, Geography, GeographyKind, SemanticBundle
from civicdecision.semantic.graph import (
    UrbanEdge,
    UrbanEdgeKind,
    UrbanGraphBundle,
    UrbanNode,
    UrbanNodeKind,
)


class GeoNamesCityRecord(StrictModel):
    geoname_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    ascii_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    feature_class: Literal["P"]
    feature_code: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    admin1_code: str | None = None
    population: int = Field(ge=0)
    timezone: str
    modification_date: date

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @classmethod
    def from_tsv(cls, line: str) -> GeoNamesCityRecord:
        values = line.split("\t")
        if len(values) != len(GEONAMES_COLUMNS):
            raise ValueError("GeoNames row does not contain 19 columns")
        row = dict(zip(GEONAMES_COLUMNS, values, strict=True))
        if row["feature_class"] != "P":
            raise ValueError("GeoNames city row must use populated-place feature class P")
        return cls(
            geoname_id=int(row["geonameid"]),
            name=row["name"],
            ascii_name=row["asciiname"] or row["name"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            feature_class=cast(Literal["P"], row["feature_class"]),
            feature_code=row["feature_code"],
            country_code=row["country_code"],
            admin1_code=row["admin1_code"] or None,
            population=int(row["population"] or 0),
            timezone=row["timezone"],
            modification_date=date.fromisoformat(row["modification_date"]),
        )


class GlobalCityCatalogEntry(StrictModel):
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    tier: Literal["G"] = "G"
    selection_rank: int = Field(ge=1)
    selection_basis: Literal["country-leader", "global-fill"]
    geoname_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    ascii_name: str = Field(min_length=1)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    admin1_code: str | None = None
    location: Coordinate
    timezone: str
    source_population: int = Field(ge=0)
    feature_code: str = Field(min_length=1)
    source_modification_date: date
    source_ref: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class GlobalCityCatalog(StrictModel):
    schema_version: str = "1.0.0"
    catalog_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    source_manifest: SourceManifest
    target_count: int = Field(ge=1)
    country_or_territory_count: int = Field(ge=1)
    selection_algorithm: str = Field(min_length=1)
    cities: list[GlobalCityCatalogEntry] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "global city catalog created_at")

    @model_validator(mode="after")
    def catalog_integrity(self) -> GlobalCityCatalog:
        if len(self.cities) != self.target_count:
            raise ValueError("global city catalog must match target_count")
        city_ids = [item.city_id for item in self.cities]
        geoname_ids = [item.geoname_id for item in self.cities]
        ranks = [item.selection_rank for item in self.cities]
        if len(city_ids) != len(set(city_ids)) or len(geoname_ids) != len(set(geoname_ids)):
            raise ValueError("global city catalog identifiers must be unique")
        if ranks != list(range(1, self.target_count + 1)):
            raise ValueError("global city catalog ranks must be contiguous and ordered")
        actual_countries = len({item.country_code for item in self.cities})
        if self.country_or_territory_count != actual_countries:
            raise ValueError("country_or_territory_count does not match the selected cities")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class CatalogArtifacts(StrictModel):
    catalog_path: Path
    coverage_matrix_path: Path
    semantic_bundle_path: Path
    graph_path: Path
    checksum_path: Path


def _load_geonames_records(
    manifest_path: Path,
) -> tuple[SourceManifest, list[GeoNamesCityRecord]]:
    manifest = validate_document(manifest_path, SourceManifest)
    manifest.verify_artifact(manifest_path.parent)
    try:
        query = GeoNamesCitiesQuery.model_validate(manifest.query)
        artifact_path = manifest_path.parent / manifest.artifact_path
        _, extracted = validate_geonames_zip(artifact_path.read_bytes(), query)
        text = extracted.decode("utf-8")
        records = [GeoNamesCityRecord.from_tsv(line) for line in text.splitlines() if line]
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AnalysisError(f"GeoNames catalog input failed validation: {exc}") from exc
    if len(records) != manifest.record_count:
        raise AnalysisError(
            f"GeoNames record count mismatch: manifest={manifest.record_count}, "
            f"parsed={len(records)}"
        )
    if len({item.geoname_id for item in records}) != len(records):
        raise AnalysisError("GeoNames catalog contains duplicate geoname identifiers")
    return manifest, records


def build_global_city_catalog(manifest_path: Path, target_count: int = 250) -> GlobalCityCatalog:
    """Select country/territory leaders, then fill by source population to target size."""

    if target_count < 1:
        raise AnalysisError("global city target_count must be positive")
    manifest, records = _load_geonames_records(manifest_path)
    ordered = sorted(records, key=lambda item: (-item.population, item.geoname_id))
    if target_count > len(ordered):
        raise AnalysisError("global city target exceeds the validated GeoNames record count")

    selected: list[tuple[GeoNamesCityRecord, Literal["country-leader", "global-fill"]]] = []
    selected_ids: set[int] = set()
    seen_countries: set[str] = set()
    for record in ordered:
        if record.country_code not in seen_countries:
            selected.append((record, "country-leader"))
            selected_ids.add(record.geoname_id)
            seen_countries.add(record.country_code)
    if len(selected) > target_count:
        selected = selected[:target_count]
        selected_ids = {record.geoname_id for record, _ in selected}
    for record in ordered:
        if len(selected) >= target_count:
            break
        if record.geoname_id not in selected_ids:
            selected.append((record, "global-fill"))
            selected_ids.add(record.geoname_id)

    entries = [
        GlobalCityCatalogEntry(
            city_id=f"geonames.{record.geoname_id}",
            selection_rank=rank,
            selection_basis=basis,
            geoname_id=record.geoname_id,
            name=record.name,
            ascii_name=record.ascii_name,
            country_code=record.country_code,
            admin1_code=record.admin1_code,
            location=Coordinate(latitude=record.latitude, longitude=record.longitude),
            timezone=record.timezone,
            source_population=record.population,
            feature_code=record.feature_code,
            source_modification_date=record.modification_date,
            source_ref=manifest.artifact_id,
            limitations=[
                "This is a gazetteer point, not an official municipal boundary.",
                "Source population values may use different years and definitions.",
                "Tier G denotes catalog discoverability, not deep analytical readiness.",
            ],
        )
        for rank, (record, basis) in enumerate(selected, start=1)
    ]
    return GlobalCityCatalog(
        catalog_id="tier-g-global-cities.v1",
        created_at=manifest.retrieved_at,
        source_manifest=manifest,
        target_count=target_count,
        country_or_territory_count=len({item.country_code for item in entries}),
        selection_algorithm=(
            "Sort validated GeoNames cities15000 records by descending source population and "
            "geoname id; select the first record for each country/territory code; then fill "
            "remaining slots from the same global order."
        ),
        cities=entries,
        limitations=[
            "Country codes include territories represented separately by GeoNames.",
            "Selection favors geographic breadth before additional high-population cities.",
            "Catalog inclusion is not evidence of data availability beyond the source point.",
        ],
    )


def build_city_semantic_bundle(catalog: GlobalCityCatalog) -> SemanticBundle:
    country_codes = sorted({item.country_code for item in catalog.cities})
    source_ref = catalog.source_manifest.artifact_id
    countries = [
        Geography(
            id=f"country.{code.lower()}",
            name=code,
            kind=GeographyKind.COUNTRY_OR_TERRITORY,
            country_code=code,
            codes={"iso-or-geonames-country-code": code},
            source_refs=[source_ref],
            limitations=[
                "The two-letter code is retained from GeoNames; this bundle does not "
                "define sovereignty."
            ],
        )
        for code in country_codes
    ]
    cities = [
        Geography(
            id=item.city_id,
            name=item.name,
            kind=GeographyKind.CITY,
            country_code=item.country_code,
            centroid=item.location,
            parent_ids=[f"country.{item.country_code.lower()}"],
            codes={"geonames": str(item.geoname_id)},
            source_refs=[source_ref],
            limitations=item.limitations,
        )
        for item in catalog.cities
    ]
    return SemanticBundle(
        bundle_id="tier-g-city-geography.v1",
        created_at=catalog.created_at,
        source_manifests=[catalog.source_manifest],
        geographies=[*countries, *cities],
        limitations=[
            "The bundle normalizes point identities only and does not supply "
            "administrative polygons."
        ],
    )


def build_city_seed_graph(catalog: GlobalCityCatalog) -> UrbanGraphBundle:
    source_ref = catalog.source_manifest.artifact_id
    country_codes = sorted({item.country_code for item in catalog.cities})
    country_nodes = [
        UrbanNode(
            id=f"country.{code.lower()}",
            kind=UrbanNodeKind.COUNTRY_OR_TERRITORY,
            label=code,
            attributes={"code": code},
            source_refs=[source_ref],
            limitations=["Code relationship follows the source gazetteer."],
        )
        for code in country_codes
    ]
    city_nodes = [
        UrbanNode(
            id=item.city_id,
            kind=UrbanNodeKind.CITY,
            label=item.name,
            attributes={
                "latitude": item.location.latitude,
                "longitude": item.location.longitude,
                "timezone": item.timezone,
                "source_population": item.source_population,
                "selection_rank": item.selection_rank,
                "selection_basis": item.selection_basis,
            },
            source_refs=[source_ref],
            limitations=item.limitations,
        )
        for item in catalog.cities
    ]
    edges = [
        UrbanEdge(
            id=f"located-in.{item.city_id}.country.{item.country_code.lower()}",
            kind=UrbanEdgeKind.LOCATED_IN,
            source_node_id=item.city_id,
            target_node_id=f"country.{item.country_code.lower()}",
            evidence_type=EvidenceType.OBSERVED,
            attributes={"source_field": "country_code"},
            source_refs=[source_ref],
            limitations=["This source-coded relationship does not adjudicate sovereignty."],
        )
        for item in catalog.cities
    ]
    return UrbanGraphBundle(
        graph_id="tier-g-city-country.v1",
        created_at=catalog.created_at,
        nodes=[*country_nodes, *city_nodes],
        edges=edges,
        source_hashes=[catalog.source_manifest.content_hash],
        limitations=[
            "This is a seed identity graph, not the targeted 100-million-edge urban graph.",
            "It contains city points and country-code relationships only.",
        ],
    )


def _write_model(path: Path, model: StrictModel) -> None:
    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    atomic_write(path, payload + b"\n")


def write_catalog_artifacts(catalog: GlobalCityCatalog, output_dir: Path) -> CatalogArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "cities-tier-g.json"
    coverage_matrix_path = output_dir / "cities-tier-g.coverage.csv"
    semantic_bundle_path = output_dir / "cities-tier-g.semantic.json"
    graph_path = output_dir / "cities-tier-g.graph.json"
    checksum_path = output_dir / "SHA256SUMS"
    semantic_bundle = build_city_semantic_bundle(catalog)
    graph = build_city_seed_graph(catalog)
    _write_model(catalog_path, catalog)
    coverage_buffer = StringIO(newline="")
    writer = csv.writer(coverage_buffer, lineterminator="\n")
    writer.writerow(
        [
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
    )
    for item in catalog.cities:
        writer.writerow(
            [
                item.selection_rank,
                item.city_id,
                item.name,
                item.country_code,
                item.timezone,
                item.location.latitude,
                item.location.longitude,
                item.source_population,
                item.selection_basis,
                item.source_modification_date.isoformat(),
            ]
        )
    atomic_write(coverage_matrix_path, coverage_buffer.getvalue().encode("utf-8"))
    _write_model(semantic_bundle_path, semantic_bundle)
    _write_model(graph_path, graph)
    GlobalCityCatalog.model_validate_json(catalog_path.read_bytes())
    SemanticBundle.model_validate_json(semantic_bundle_path.read_bytes())
    UrbanGraphBundle.model_validate_json(graph_path.read_bytes())
    entries = [
        f"{sha256_file(path)[7:]}  {path.name}"
        for path in (
            catalog_path,
            coverage_matrix_path,
            semantic_bundle_path,
            graph_path,
        )
    ]
    atomic_write(checksum_path, ("\n".join(entries) + "\n").encode("ascii"))
    return CatalogArtifacts(
        catalog_path=catalog_path,
        coverage_matrix_path=coverage_matrix_path,
        semantic_bundle_path=semantic_bundle_path,
        graph_path=graph_path,
        checksum_path=checksum_path,
    )
