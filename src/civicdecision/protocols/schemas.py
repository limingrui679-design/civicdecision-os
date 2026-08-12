"""Generate the three stable public JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from civicdecision.protocols.city import CityAdapterManifest
from civicdecision.protocols.decision import DecisionPack
from civicdecision.protocols.scenario import PolicyScenario

SCHEMAS: dict[str, type[BaseModel]] = {
    "city-adapter.schema.json": CityAdapterManifest,
    "policy-scenario.schema.json": PolicyScenario,
    "decision-pack.schema.json": DecisionPack,
}


def build_schemas(output_dir: Path) -> list[Path]:
    """Write deterministic Pydantic JSON Schemas."""

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for filename, model in SCHEMAS.items():
        path = output_dir / filename
        content = json.dumps(
            model.model_json_schema(mode="validation"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        path.write_text(f"{content}\n", encoding="utf-8")
        created.append(path)
    return created
