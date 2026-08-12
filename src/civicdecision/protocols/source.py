"""Versioned public-data source manifests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from civicdecision.errors import IntegrityError
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    SHA256_PATTERN,
    JsonValue,
    StrictModel,
    ensure_aware,
    sha256_file,
)


class SourceManifest(StrictModel):
    """Evidence required to identify and independently verify a downloaded artifact."""

    schema_version: str = "1.0.0"
    source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    landing_url: AnyHttpUrl
    data_url: AnyHttpUrl
    license: str = Field(min_length=1)
    retrieved_at: datetime
    upstream_updated_at: datetime | None = None
    query: dict[str, JsonValue]
    artifact_path: str = Field(min_length=1)
    content_hash: str
    record_count: int = Field(ge=0)
    schema_fingerprint: str
    geographic_scope: str = Field(min_length=1)
    temporal_scope: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    response_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def retrieved_must_be_aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "retrieved_at")

    @field_validator("upstream_updated_at")
    @classmethod
    def upstream_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            return ensure_aware(value, "upstream_updated_at")
        return value

    @field_validator("content_hash", "schema_fingerprint")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("digest must use sha256:<64 lowercase hex characters>")
        return value

    @model_validator(mode="after")
    def update_cannot_follow_retrieval(self) -> SourceManifest:
        if self.upstream_updated_at and self.upstream_updated_at > self.retrieved_at:
            raise ValueError("upstream_updated_at cannot be later than retrieved_at")
        return self

    def verify_artifact(self, root: Path) -> None:
        """Raise when the stored artifact does not match its manifest."""

        artifact = (root / self.artifact_path).resolve()
        root_resolved = root.resolve()
        if not artifact.is_relative_to(root_resolved):
            raise IntegrityError("artifact path escapes the declared root")
        if not artifact.is_file():
            raise IntegrityError(f"artifact does not exist: {artifact}")
        actual = sha256_file(artifact)
        if actual != self.content_hash:
            raise IntegrityError(
                f"artifact hash mismatch: expected {self.content_hash}, got {actual}"
            )
