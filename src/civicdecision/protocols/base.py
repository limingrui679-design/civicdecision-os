"""Shared protocol primitives and canonical serialization."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import JsonValue as JsonValue

IDENTIFIER_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class StrictModel(BaseModel):
    """Base model that forbids silent protocol drift."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        allow_inf_nan=False,
    )


class IdentifiedModel(StrictModel):
    """Base model with a stable lowercase identifier."""

    id: str

    @field_validator("id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not re.fullmatch(IDENTIFIER_PATTERN, value):
            raise ValueError("identifier must be lowercase and use only . _ - separators")
        return value


def ensure_aware(value: datetime, field_name: str) -> datetime:
    """Reject timezone-naive datetimes at protocol boundaries."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


def normalize_float(value: float, *, significant_digits: int) -> float:
    """Round one finite float to a portable number of significant digits."""

    if not 1 <= significant_digits <= 17:
        raise ValueError("significant_digits must be between 1 and 17")
    normalized = float(format(value, f".{significant_digits}g"))
    return 0.0 if normalized == 0.0 else normalized


def normalize_json_floats(value: Any, *, significant_digits: int) -> Any:
    """Round every float in a JSON-compatible value."""

    if isinstance(value, float):
        return normalize_float(value, significant_digits=significant_digits)
    if isinstance(value, list):
        return [
            normalize_json_floats(item, significant_digits=significant_digits) for item in value
        ]
    if isinstance(value, dict):
        return {
            key: normalize_json_floats(item, significant_digits=significant_digits)
            for key, item in value.items()
        }
    return value


def canonical_json(
    value: BaseModel | JsonValue | dict[str, Any],
    *,
    float_significant_digits: int | None = None,
) -> bytes:
    """Serialize JSON deterministically for hashing and golden vectors."""

    if isinstance(value, BaseModel):
        payload: Any = value.model_dump(mode="json", exclude_none=True)
    else:
        payload = value
    if float_significant_digits is not None:
        payload = normalize_json_floats(
            payload,
            significant_digits=float_significant_digits,
        )
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    """Return a namespaced SHA-256 digest."""

    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def sha256_file(path: Path) -> str:
    """Hash a file without loading the whole artifact into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def schema_fingerprint(records: list[dict[str, Any]]) -> str:
    """Fingerprint observed field names and value types for drift detection."""

    fields: dict[str, set[str]] = {}
    for record in records:
        for key, value in record.items():
            fields.setdefault(key, set()).add(type(value).__name__)
    normalized = {key: sorted(types) for key, types in sorted(fields.items())}
    return sha256_bytes(canonical_json(normalized))
