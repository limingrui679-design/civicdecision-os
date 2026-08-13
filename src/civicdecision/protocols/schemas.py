"""Generate stable public protocol and semantic JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from civicdecision.analysis.causal import DifferenceInDifferencesRun
from civicdecision.analysis.forecasting import ForecastRun
from civicdecision.analysis.simulation import SimulationRun
from civicdecision.analysis.uncertainty import UncertaintyRun
from civicdecision.benchmarks.models import (
    BenchmarkEvidenceSummary,
    BenchmarkRegistry,
    HistoricalReplay,
)
from civicdecision.optimization.portfolio import PortfolioOptimizationRun
from civicdecision.protocols.city import CityAdapterManifest
from civicdecision.protocols.decision import DecisionPack
from civicdecision.protocols.scenario import PolicyScenario
from civicdecision.semantic.city_catalog import GlobalCityCatalog
from civicdecision.semantic.core import SemanticBundle
from civicdecision.semantic.graph import UrbanGraphBundle
from civicdecision.standardized.models import (
    StandardizedCityBundle,
    StandardScenarioRun,
    TierSRegistry,
)

SCHEMAS: dict[str, type[BaseModel]] = {
    "benchmark-evidence-summary.schema.json": BenchmarkEvidenceSummary,
    "benchmark-registry.schema.json": BenchmarkRegistry,
    "causal-run.schema.json": DifferenceInDifferencesRun,
    "city-adapter.schema.json": CityAdapterManifest,
    "policy-scenario.schema.json": PolicyScenario,
    "decision-pack.schema.json": DecisionPack,
    "forecast-run.schema.json": ForecastRun,
    "global-city-catalog.schema.json": GlobalCityCatalog,
    "historical-replay.schema.json": HistoricalReplay,
    "semantic-bundle.schema.json": SemanticBundle,
    "urban-graph.schema.json": UrbanGraphBundle,
    "standard-scenario-run.schema.json": StandardScenarioRun,
    "standardized-city-bundle.schema.json": StandardizedCityBundle,
    "tier-s-registry.schema.json": TierSRegistry,
    "portfolio-optimization-run.schema.json": PortfolioOptimizationRun,
    "simulation-run.schema.json": SimulationRun,
    "uncertainty-run.schema.json": UncertaintyRun,
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
