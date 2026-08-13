from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from civicdecision.plugins import (
    PluginCapability,
    PluginManifest,
    PluginRegistry,
    PluginValidationError,
    load_plugin_package,
    scaffold_plugin,
)
from civicdecision.protocols.base import sha256_bytes


def create_starter(tmp_path: Path, plugin_id: str = "review.adapter") -> Path:
    root = tmp_path / plugin_id
    scaffold_plugin(root, plugin_id=plugin_id, name="Review Adapter", author="Reviewer")
    return root


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, object]) -> bytes:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    path.write_bytes(content)
    return content


def rehash_adapter(root: Path) -> None:
    manifest_path = root / "plugin.json"
    manifest = read_json(manifest_path)
    relative = str(manifest["adapter_paths"][0])  # type: ignore[index]
    manifest["artifact_hashes"] = {relative: sha256_bytes((root / relative).read_bytes())}
    write_json(manifest_path, manifest)


def test_scaffold_creates_immediately_valid_data_only_package(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    package = load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})
    assert sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    ) == [
        "adapters/sample-city.json",
        "plugin.json",
    ]
    assert package.manifest.enabled_by_default is False
    assert package.manifest.capabilities == [PluginCapability.CITY_ADAPTER]
    assert package.adapters[0].city_id == "review.adapter.sample-city"
    assert package.package_hash.startswith("sha256:")


def test_plugin_package_hash_is_deterministic(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    first = load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})
    second = load_plugin_package(root, allowlisted_plugin_ids=frozenset({"review.adapter"}))
    assert first == second
    assert first.package_hash == second.package_hash


def test_plugin_must_be_explicitly_allowlisted(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    with pytest.raises(PluginValidationError, match="not explicitly allowlisted"):
        load_plugin_package(root, allowlisted_plugin_ids={"different.adapter"})


def test_plugin_hash_tampering_fails_closed(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    adapter = root / "adapters/sample-city.json"
    adapter.write_bytes(adapter.read_bytes() + b" ")
    with pytest.raises(PluginValidationError, match="hash mismatch"):
        load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})


def test_plugin_rejects_unmanifested_executable_or_extra_artifact(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    (root / "plugin.py").write_text("raise RuntimeError('must never execute')\n", encoding="utf-8")
    with pytest.raises(PluginValidationError, match="inventory differs"):
        load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})


def test_plugin_rejects_symbolic_links(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    target = root / "adapters/sample-city.json"
    link = root / "unexpected-link.json"
    os.symlink(target, link)
    with pytest.raises(PluginValidationError, match="symbolic links"):
        load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})


def test_plugin_rejects_missing_and_invalid_roots(tmp_path: Path) -> None:
    with pytest.raises(PluginValidationError, match="unavailable"):
        load_plugin_package(tmp_path / "missing", allowlisted_plugin_ids={"review.adapter"})
    file_root = tmp_path / "file"
    file_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(PluginValidationError, match="regular directory"):
        load_plugin_package(file_root, allowlisted_plugin_ids={"review.adapter"})


def test_plugin_rejects_invalid_manifest_and_adapter_documents(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    (root / "plugin.json").write_text("{invalid", encoding="utf-8")
    with pytest.raises(PluginValidationError, match="invalid plugin manifest"):
        load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})

    second = create_starter(tmp_path, "invalid.adapter")
    adapter = second / "adapters/sample-city.json"
    adapter.write_text("{}\n", encoding="utf-8")
    rehash_adapter(second)
    with pytest.raises(PluginValidationError, match="invalid city adapter"):
        load_plugin_package(second, allowlisted_plugin_ids={"invalid.adapter"})


def test_plugin_rejects_empty_or_oversized_artifact(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    adapter = root / "adapters/sample-city.json"
    adapter.write_bytes(b"")
    rehash_adapter(root)
    with pytest.raises(PluginValidationError, match="size outside"):
        load_plugin_package(root, allowlisted_plugin_ids={"review.adapter"})


def test_plugin_registry_registers_and_summarizes_package(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    registry = PluginRegistry(["review.adapter"])
    package = registry.register(root)
    summaries = registry.summaries()
    assert registry.packages == (package,)
    assert len(summaries) == 1
    assert summaries[0].city_adapters == 1
    assert summaries[0].city_ids == ["review.adapter.sample-city"]
    assert summaries[0].package_hash == package.package_hash


def test_plugin_registry_rejects_duplicate_registration(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    registry = PluginRegistry(["review.adapter"])
    registry.register(root)
    with pytest.raises(PluginValidationError, match="already registered"):
        registry.register(root)


def test_plugin_registry_rejects_city_identifier_overlap(tmp_path: Path) -> None:
    first = create_starter(tmp_path, "first.adapter")
    second = create_starter(tmp_path, "second.adapter")
    second_adapter_path = second / "adapters/sample-city.json"
    second_adapter = read_json(second_adapter_path)
    second_adapter["city_id"] = "first.adapter.sample-city"
    write_json(second_adapter_path, second_adapter)
    rehash_adapter(second)
    registry = PluginRegistry(["first.adapter", "second.adapter"])
    registry.register(first)
    with pytest.raises(PluginValidationError, match="overlap"):
        registry.register(second)


def test_plugin_registry_capacity_is_bounded(tmp_path: Path) -> None:
    first = create_starter(tmp_path, "first.adapter")
    second = create_starter(tmp_path, "second.adapter")
    registry = PluginRegistry(["first.adapter", "second.adapter"], max_plugins=1)
    registry.register(first)
    with pytest.raises(PluginValidationError, match="capacity"):
        registry.register(second)


def test_plugin_registry_requires_nonempty_sorted_unique_allowlist() -> None:
    for allowlist in ([], ["b.adapter", "a.adapter"], ["a.adapter", "a.adapter"]):
        with pytest.raises(ValueError, match="allowlist"):
            PluginRegistry(allowlist)


@pytest.mark.parametrize("maximum", [0, 129])
def test_plugin_registry_validates_capacity(maximum: int) -> None:
    with pytest.raises(ValueError, match="max_plugins"):
        PluginRegistry(["a.adapter"], max_plugins=maximum)


def test_plugin_scaffold_never_overwrites_existing_directory(tmp_path: Path) -> None:
    root = create_starter(tmp_path)
    original = (root / "plugin.json").read_bytes()
    with pytest.raises(FileExistsError, match="already exists"):
        scaffold_plugin(root, plugin_id="review.adapter", name="Other", author="Other")
    assert (root / "plugin.json").read_bytes() == original


def test_plugin_manifest_rejects_unsafe_contract_mutations() -> None:
    mutations = [
        (lambda payload: payload.update(enabled_by_default=True), "False"),
        (lambda payload: payload.update(capabilities=["source-binding"]), "city-adapter"),
        (lambda payload: payload.update(adapter_paths=["../escape.json"]), "adapters"),
        (
            lambda payload: payload.update(adapter_paths=["adapters/a.json", "adapters/a.json"]),
            "sorted and unique",
        ),
        (
            lambda payload: payload.update(
                artifact_hashes={"adapters/sample-city.json": "invalid"}
            ),
            "SHA-256",
        ),
        (
            lambda payload: payload.update(
                artifact_hashes={"adapters/other.json": "sha256:" + "0" * 64}
            ),
            "must match",
        ),
    ]
    for mutation, message in mutations:
        payload = {
            "plugin_id": "review.adapter",
            "name": "Review Adapter",
            "version": "1.0.0",
            "description": "Fixture package.",
            "author": "Reviewer",
            "license": "MIT",
            "capabilities": ["city-adapter"],
            "adapter_paths": ["adapters/sample-city.json"],
            "artifact_hashes": {"adapters/sample-city.json": "sha256:" + "0" * 64},
            "evidence_boundary": ["Fixture only."],
            "enabled_by_default": False,
        }
        mutation(payload)
        with pytest.raises(ValidationError, match=message):
            PluginManifest.model_validate(payload)
