"""Constrained plugin loader with exact allowlists and no code execution."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from civicdecision.errors import CivicDecisionError
from civicdecision.plugins.models import PluginManifest, PluginPackage, PluginPackageSummary
from civicdecision.protocols.base import canonical_json, sha256_bytes, sha256_file
from civicdecision.protocols.city import CityAdapterManifest

MAX_MANIFEST_BYTES = 512 * 1024
MAX_ADAPTER_BYTES = 2 * 1024 * 1024


class PluginValidationError(CivicDecisionError):
    """A plugin directory violated a package, integrity, or allowlist boundary."""


def _bounded_file(root: Path, relative: str, *, max_bytes: int) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = root / relative
    if candidate.is_symlink():
        raise PluginValidationError(f"plugin artifacts cannot be symbolic links: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as exc:
        raise PluginValidationError(f"plugin artifact is missing: {relative}") from exc
    if not resolved.is_relative_to(root_resolved):
        raise PluginValidationError(f"plugin artifact escapes package root: {relative}")
    if not resolved.is_file():
        raise PluginValidationError(f"plugin artifact is not a regular file: {relative}")
    size = resolved.stat().st_size
    if size <= 0 or size > max_bytes:
        raise PluginValidationError(
            f"plugin artifact size outside 1..{max_bytes} bytes: {relative} ({size})"
        )
    return resolved


def _parse_manifest(root: Path) -> PluginManifest:
    path = _bounded_file(root, "plugin.json", max_bytes=MAX_MANIFEST_BYTES)
    try:
        return PluginManifest.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise PluginValidationError(f"invalid plugin manifest: {exc}") from exc


def load_plugin_package(
    root: Path,
    *,
    allowlisted_plugin_ids: set[str] | frozenset[str],
) -> PluginPackage:
    """Load one exact-allowlisted, data-only package without importing Python code."""

    try:
        if root.is_symlink() or not root.resolve(strict=True).is_dir():
            raise PluginValidationError(f"plugin root is not a regular directory: {root}")
    except (FileNotFoundError, RuntimeError) as exc:
        raise PluginValidationError(f"plugin root is unavailable: {root}") from exc
    manifest = _parse_manifest(root)
    if manifest.plugin_id not in allowlisted_plugin_ids:
        raise PluginValidationError(f"plugin is not explicitly allowlisted: {manifest.plugin_id}")

    expected_files = {"plugin.json", *manifest.adapter_paths}
    observed_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PluginValidationError(
                f"plugin package cannot contain symbolic links: {path.relative_to(root)}"
            )
        if path.is_file():
            observed_files.add(path.relative_to(root).as_posix())
    unexpected = observed_files - expected_files
    missing = expected_files - observed_files
    if unexpected or missing:
        raise PluginValidationError(
            "plugin package inventory differs from its manifest: "
            f"unexpected={sorted(unexpected)}, missing={sorted(missing)}"
        )

    adapters: list[CityAdapterManifest] = []
    verified_hashes: dict[str, str] = {}
    for relative in manifest.adapter_paths:
        path = _bounded_file(root, relative, max_bytes=MAX_ADAPTER_BYTES)
        actual_hash = sha256_file(path)
        expected_hash = manifest.artifact_hashes[relative]
        if actual_hash != expected_hash:
            raise PluginValidationError(
                f"plugin artifact hash mismatch for {relative}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        try:
            adapter = CityAdapterManifest.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as exc:
            raise PluginValidationError(f"invalid city adapter {relative}: {exc}") from exc
        adapters.append(adapter)
        verified_hashes[relative] = actual_hash

    city_ids = [adapter.city_id for adapter in adapters]
    if len(city_ids) != len(set(city_ids)):
        raise PluginValidationError("plugin contains duplicate city adapter identifiers")
    package_hash = sha256_bytes(
        canonical_json(
            {
                "manifest": json.loads(canonical_json(manifest)),
                "verified_artifacts": verified_hashes,
            }
        )
    )
    try:
        return PluginPackage(
            manifest=manifest,
            adapters=adapters,
            package_hash=package_hash,
        )
    except ValidationError as exc:
        raise PluginValidationError(f"plugin package does not reconcile: {exc}") from exc


class PluginRegistry:
    """In-memory registry that rejects unlisted, duplicate, or overlapping packages."""

    def __init__(self, allowlisted_plugin_ids: list[str], *, max_plugins: int = 32) -> None:
        if not 1 <= max_plugins <= 128:
            raise ValueError("plugin registry max_plugins must be between 1 and 128")
        if allowlisted_plugin_ids != sorted(set(allowlisted_plugin_ids)):
            raise ValueError("plugin allowlist must be sorted and unique")
        if not allowlisted_plugin_ids:
            raise ValueError("plugin registry requires a non-empty exact allowlist")
        self._allowlist = frozenset(allowlisted_plugin_ids)
        self._max_plugins = max_plugins
        self._packages: dict[str, PluginPackage] = {}

    @property
    def packages(self) -> tuple[PluginPackage, ...]:
        return tuple(self._packages[key] for key in sorted(self._packages))

    def register(self, root: Path) -> PluginPackage:
        if len(self._packages) >= self._max_plugins:
            raise PluginValidationError("plugin registry capacity reached")
        package = load_plugin_package(root, allowlisted_plugin_ids=self._allowlist)
        plugin_id = package.manifest.plugin_id
        if plugin_id in self._packages:
            raise PluginValidationError(f"plugin already registered: {plugin_id}")
        existing_cities = {
            adapter.city_id
            for installed in self._packages.values()
            for adapter in installed.adapters
        }
        overlap = existing_cities.intersection(adapter.city_id for adapter in package.adapters)
        if overlap:
            raise PluginValidationError(
                f"plugin city identifiers overlap registered packages: {', '.join(sorted(overlap))}"
            )
        self._packages[plugin_id] = package
        return package

    def summaries(self) -> list[PluginPackageSummary]:
        return [
            PluginPackageSummary(
                plugin_id=package.manifest.plugin_id,
                name=package.manifest.name,
                version=package.manifest.version,
                capabilities=package.manifest.capabilities,
                city_adapters=len(package.adapters),
                city_ids=sorted(adapter.city_id for adapter in package.adapters),
                package_hash=package.package_hash,
                evidence_boundary=package.manifest.evidence_boundary,
            )
            for package in self.packages
        ]


__all__ = [
    "MAX_ADAPTER_BYTES",
    "MAX_MANIFEST_BYTES",
    "PluginRegistry",
    "PluginValidationError",
    "load_plugin_package",
]
