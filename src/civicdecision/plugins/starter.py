"""Deterministic starter package generator for adapter authors."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from civicdecision.connectors.base import atomic_write
from civicdecision.plugins.models import PluginCapability, PluginManifest
from civicdecision.protocols.base import sha256_bytes
from civicdecision.protocols.city import BoundingBox, CityAdapterManifest, CityTier, CoverageWindow


def _pretty_json(document: BaseModel) -> bytes:
    payload = document.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def scaffold_plugin(output: Path, *, plugin_id: str, name: str, author: str) -> list[Path]:
    """Create a non-overwriting, immediately valid data-only adapter starter."""

    if output.exists():
        raise FileExistsError(f"plugin output already exists: {output}")
    adapter = CityAdapterManifest(
        city_id=f"{plugin_id}.sample-city",
        display_name=f"{name} Sample City",
        country_code="ZZ",
        tier=CityTier.GLOBAL,
        timezone="UTC",
        bbox=BoundingBox(west=-0.1, south=-0.1, east=0.1, north=0.1),
        coverage=CoverageWindow(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        source_ids=[f"{plugin_id}.sample-source"],
        capabilities=["catalog.discovery"],
        data_gaps=["Replace the starter identity and bind versioned source evidence."],
        limitations=[
            "This generated adapter is a starter fixture and does not establish analytical "
            "readiness."
        ],
    )
    adapter_bytes = _pretty_json(adapter)
    relative = "adapters/sample-city.json"
    manifest = PluginManifest(
        plugin_id=plugin_id,
        name=name,
        version="0.1.0",
        description="Data-only CivicDecision city adapter starter.",
        author=author,
        license="MIT",
        capabilities=[PluginCapability.CITY_ADAPTER],
        adapter_paths=[relative],
        artifact_hashes={relative: sha256_bytes(adapter_bytes)},
        evidence_boundary=[
            "Installing an adapter does not establish source quality, local readiness, "
            "deployment, adoption, or impact."
        ],
    )
    adapter_path = output / relative
    manifest_path = output / "plugin.json"
    adapter_path.parent.mkdir(parents=True, exist_ok=False)
    atomic_write(adapter_path, adapter_bytes)
    atomic_write(manifest_path, _pretty_json(manifest))
    return [manifest_path, adapter_path]


__all__ = ["scaffold_plugin"]
