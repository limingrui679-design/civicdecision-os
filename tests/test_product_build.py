from __future__ import annotations

import json
from pathlib import Path

import pytest

from civicdecision.errors import IntegrityError
from civicdecision.product.build import ProductArtifactManifest, build_product_artifacts
from civicdecision.protocols.base import sha256_file

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def rebuilt_product(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("product-artifacts") / "product"
    build_product_artifacts(ROOT, output)
    return output


def test_product_build_exactly_matches_committed_projection(rebuilt_product: Path) -> None:
    committed = ROOT / "catalog/product"
    expected = sorted(
        path.relative_to(committed) for path in committed.rglob("*") if path.is_file()
    )
    actual = sorted(
        path.relative_to(rebuilt_product) for path in rebuilt_product.rglob("*") if path.is_file()
    )
    assert expected == actual
    assert len(actual) == 338
    for relative in expected:
        assert (committed / relative).read_bytes() == (rebuilt_product / relative).read_bytes()


def test_product_manifest_covers_every_projected_artifact(rebuilt_product: Path) -> None:
    manifest = ProductArtifactManifest.model_validate_json(
        (rebuilt_product / "artifact-manifest.json").read_bytes()
    )
    assert manifest.artifact_count == 336
    assert len(manifest.artifacts) == 336
    assert manifest.catalog_fingerprint.startswith("sha256:")
    for entry in manifest.artifacts:
        path = rebuilt_product / entry.path
        assert path.stat().st_size == entry.byte_count
        assert sha256_file(path) == entry.content_hash


def test_product_checksum_inventory_is_relative_complete_and_valid(rebuilt_product: Path) -> None:
    lines = (rebuilt_product / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    assert len(lines) == 337
    observed = set()
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert not relative.startswith("/") and ".." not in Path(relative).parts
        assert sha256_file(rebuilt_product / relative) == f"sha256:{digest}"
        observed.add(relative)
    assert observed == {
        path.relative_to(rebuilt_product).as_posix()
        for path in rebuilt_product.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }


def test_product_collections_publish_exact_record_counts(rebuilt_product: Path) -> None:
    expected = {
        "cities/highest-available.json": 258,
        "cities/tier-g.json": 250,
        "cities/tier-s.json": 30,
        "cities/tier-d.json": 8,
        "scenarios/all.json": 188,
        "scenarios/standard-screen.json": 90,
        "scenarios/deep-pack.json": 96,
        "scenarios/reference-pack.json": 2,
        "scenarios/decision-pack.json": 98,
        "sources/index.json": 90,
        "suites/index.json": 7,
        "designs/index.json": 240,
        "designs/reference-implemented.json": 12,
        "designs/design-only.json": 228,
        "designs/suite/climate-disaster-resilience.json": 40,
        "designs/decision-type/evaluate.json": 30,
        "design-families/index.json": 30,
    }
    for relative, count in expected.items():
        document = json.loads((rebuilt_product / relative).read_text(encoding="utf-8"))
        assert document["record_count"] == len(document["items"]) == count
        assert document["claim_boundary"]
    design_details = sorted((rebuilt_product / "designs/detail").glob("*.json"))
    family_details = sorted((rebuilt_product / "design-families/detail").glob("*.json"))
    assert len(design_details) == 240
    assert len(family_details) == 30
    assert all(
        json.loads(path.read_text())["design"]["city_bindings"] == [] for path in design_details
    )
    evidence = json.loads((rebuilt_product / "evidence/scenario-library-summary.json").read_text())
    assert (evidence["design_count"], evidence["family_count"]) == (240, 30)
    assert evidence["city_bound_executions_counted"] == evidence["methods_claimed"] == 0


def test_product_schemas_and_openapi_are_substantive(rebuilt_product: Path) -> None:
    schemas = sorted((rebuilt_product / "schemas").glob("*.schema.json"))
    openapi = json.loads((rebuilt_product / "openapi-v1.json").read_text(encoding="utf-8"))
    web = json.loads((rebuilt_product / "web-assets.json").read_text(encoding="utf-8"))
    assert len(schemas) == 28
    assert all(
        "$defs" in json.loads(path.read_text(encoding="utf-8"))
        or "properties" in json.loads(path.read_text(encoding="utf-8"))
        for path in schemas
    )
    assert len(openapi["paths"]) == 19
    assert len(web["assets"]) == web["asset_count"] == 4
    assert all(item["content_hash"].startswith("sha256:") for item in web["assets"])


def test_product_builder_allows_exact_regeneration_in_place(rebuilt_product: Path) -> None:
    before = {
        path.relative_to(rebuilt_product): path.read_bytes()
        for path in rebuilt_product.rglob("*")
        if path.is_file()
    }
    result = build_product_artifacts(ROOT, rebuilt_product)
    after = {
        path.relative_to(rebuilt_product): path.read_bytes()
        for path in rebuilt_product.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert len(result.artifact_paths) == 338


def test_product_builder_rejects_unexpected_stale_files(tmp_path: Path) -> None:
    output = tmp_path / "product"
    output.mkdir()
    (output / "stale.txt").write_text("untracked", encoding="utf-8")
    with pytest.raises(IntegrityError, match="unexpected files"):
        build_product_artifacts(ROOT, output)
