from __future__ import annotations

from datetime import UTC, datetime

import pytest

from civicdecision.protocols.source import SourceManifest


@pytest.fixture
def source_manifest() -> SourceManifest:
    return SourceManifest(
        source_id="test-source",
        artifact_id="test-source-page-1",
        name="Test source",
        publisher="Test publisher",
        landing_url="https://example.com/landing",
        data_url="https://example.com/data.json",
        license="Test-only fixture",
        retrieved_at=datetime(2026, 8, 12, tzinfo=UTC),
        upstream_updated_at=datetime(2026, 8, 11, tzinfo=UTC),
        query={"limit": 2},
        artifact_path="artifact.json",
        content_hash="sha256:" + "0" * 64,
        record_count=2,
        schema_fingerprint="sha256:" + "1" * 64,
        geographic_scope="fixture",
        temporal_scope="fixture",
        limitations=["Fixture data are not empirical evidence."],
    )
