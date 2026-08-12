"""Connector primitives."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import Field

from civicdecision.protocols.base import StrictModel, canonical_json
from civicdecision.protocols.source import SourceManifest


class FetchResult(StrictModel):
    artifact_path: Path
    manifest_path: Path
    manifest: SourceManifest
    warnings: list[str] = Field(default_factory=list)


def atomic_write(path: Path, content: bytes) -> None:
    """Write a complete artifact without exposing partial files."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_manifest(path: Path, manifest: SourceManifest) -> None:
    """Write a human-readable manifest using canonical values."""

    payload = json.loads(canonical_json(manifest))
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    atomic_write(path, content + b"\n")
