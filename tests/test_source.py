from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from civicdecision.errors import IntegrityError
from civicdecision.protocols.base import sha256_bytes
from civicdecision.protocols.source import SourceManifest


def test_source_manifest_verifies_artifact(tmp_path: Path, source_manifest: SourceManifest) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"[]")
    source_manifest.content_hash = sha256_bytes(b"[]")
    source_manifest.verify_artifact(tmp_path)


def test_source_manifest_detects_tampering(tmp_path: Path, source_manifest: SourceManifest) -> None:
    (tmp_path / "artifact.json").write_bytes(b"changed")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        source_manifest.verify_artifact(tmp_path)


def test_source_manifest_rejects_missing_artifact(
    tmp_path: Path, source_manifest: SourceManifest
) -> None:
    with pytest.raises(IntegrityError, match="does not exist"):
        source_manifest.verify_artifact(tmp_path)


def test_source_manifest_rejects_path_escape(
    tmp_path: Path, source_manifest: SourceManifest
) -> None:
    source_manifest.artifact_path = "../outside.json"
    with pytest.raises(IntegrityError, match="escapes"):
        source_manifest.verify_artifact(tmp_path)


def test_source_manifest_rejects_future_upstream_time(source_manifest: SourceManifest) -> None:
    payload = source_manifest.model_dump(mode="json")
    payload["upstream_updated_at"] = "2026-08-13T00:00:00Z"
    with pytest.raises(ValidationError, match="cannot be later"):
        SourceManifest.model_validate(payload)


def test_source_manifest_rejects_invalid_digest(source_manifest: SourceManifest) -> None:
    payload = source_manifest.model_dump(mode="json")
    payload["content_hash"] = "not-a-hash"
    with pytest.raises(ValidationError, match="sha256"):
        SourceManifest.model_validate(payload)


def test_source_manifest_rejects_naive_upstream_time(
    source_manifest: SourceManifest,
) -> None:
    payload = source_manifest.model_dump()
    payload["upstream_updated_at"] = payload["upstream_updated_at"].replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone"):
        SourceManifest.model_validate(payload)
