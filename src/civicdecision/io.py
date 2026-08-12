"""Protocol document loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from civicdecision.errors import ProtocolError

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_document(path: Path) -> Any:
    """Load JSON or YAML without guessing unsupported formats."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError(f"cannot read protocol document: {path}") from exc
    try:
        if path.suffix.lower() == ".json":
            return json.loads(text)
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ProtocolError(f"invalid {path.suffix} document: {path}") from exc
    raise ProtocolError("protocol documents must use .json, .yaml, or .yml")


def validate_document(path: Path, model: type[ModelT]) -> ModelT:
    """Load and validate a protocol document with a typed error."""

    try:
        return model.model_validate(load_document(path))
    except ValidationError as exc:
        raise ProtocolError(str(exc)) from exc
