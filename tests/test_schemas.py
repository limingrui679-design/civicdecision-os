from __future__ import annotations

from pathlib import Path

from civicdecision.protocols.schemas import build_schemas


def test_schema_generation_is_deterministic(tmp_path: Path) -> None:
    first = build_schemas(tmp_path / "first")
    second = build_schemas(tmp_path / "second")
    assert [path.name for path in first] == [path.name for path in second]
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    assert len(first) == 3
