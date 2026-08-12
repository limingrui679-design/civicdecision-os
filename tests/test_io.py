from __future__ import annotations

from pathlib import Path

import pytest

from civicdecision.errors import ProtocolError
from civicdecision.io import load_document, validate_document
from civicdecision.protocols.city import CityAdapterManifest


def test_load_document_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProtocolError, match="cannot read"):
        load_document(tmp_path / "missing.json")


def test_load_document_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ProtocolError, match=r"invalid \.json"):
        load_document(path)


def test_load_document_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("key: [", encoding="utf-8")
    with pytest.raises(ProtocolError, match=r"invalid \.yaml"):
        load_document(path)


def test_load_document_rejects_unknown_extension(tmp_path: Path) -> None:
    path = tmp_path / "document.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(ProtocolError, match="must use"):
        load_document(path)


def test_validate_document_wraps_model_error(tmp_path: Path) -> None:
    path = tmp_path / "city.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ProtocolError, match="city_id"):
        validate_document(path, CityAdapterManifest)
