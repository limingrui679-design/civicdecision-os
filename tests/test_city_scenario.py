from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from civicdecision.io import validate_document
from civicdecision.protocols.city import BoundingBox, CityAdapterManifest, CoverageWindow
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.scenario import PolicyScenario

ROOT = Path(__file__).parents[1]


def test_example_city_adapter_validates() -> None:
    city = validate_document(ROOT / "examples/cities/boston-cambridge.yaml", CityAdapterManifest)
    assert city.city_id == "us.ma.boston-cambridge"
    assert city.country_code == "US"


def test_city_adapter_rejects_unknown_timezone() -> None:
    city = validate_document(ROOT / "examples/cities/boston-cambridge.yaml", CityAdapterManifest)
    payload = city.model_dump()
    payload["timezone"] = "Mars/Olympus_Mons"
    with pytest.raises(ValidationError, match="unknown IANA timezone"):
        CityAdapterManifest.model_validate(payload)


def test_city_adapter_rejects_duplicate_sources() -> None:
    city = validate_document(ROOT / "examples/cities/boston-cambridge.yaml", CityAdapterManifest)
    payload = city.model_dump()
    payload["source_ids"] = ["same", "same"]
    with pytest.raises(ValidationError, match="unique"):
        CityAdapterManifest.model_validate(payload)


def test_bounding_box_and_coverage_are_ordered() -> None:
    with pytest.raises(ValidationError, match="west < east"):
        BoundingBox(west=5, east=4, south=1, north=2)
    with pytest.raises(ValidationError, match="coverage start"):
        CoverageWindow(start="2026-01-02T00:00:00Z", end="2026-01-01T00:00:00Z")


def test_city_adapter_rejects_nonletter_country_code() -> None:
    city = validate_document(ROOT / "examples/cities/boston-cambridge.yaml", CityAdapterManifest)
    payload = city.model_dump()
    payload["country_code"] = "U1"
    with pytest.raises(ValidationError, match="letters only"):
        CityAdapterManifest.model_validate(payload)


def test_example_scenario_validates() -> None:
    scenario = validate_document(
        ROOT / "examples/scenarios/boston-heat-transit.yaml", PolicyScenario
    )
    assert scenario.random_seed == 20260812
    assert EvidenceType.OPTIMIZED in scenario.evidence_requirements


def test_scenario_rejects_future_data_cutoff() -> None:
    scenario = validate_document(
        ROOT / "examples/scenarios/boston-heat-transit.yaml", PolicyScenario
    )
    payload = scenario.model_dump(mode="json")
    payload["data_cutoff"] = "2025-07-02T00:00:00-04:00"
    with pytest.raises(ValidationError, match="data_cutoff"):
        PolicyScenario.model_validate(payload)


def test_causal_mode_requires_causal_evidence() -> None:
    scenario = validate_document(
        ROOT / "examples/scenarios/boston-heat-transit.yaml", PolicyScenario
    )
    payload = scenario.model_dump(mode="json")
    payload["analysis_modes"].append("causal")
    with pytest.raises(ValidationError, match="causal evidence"):
        PolicyScenario.model_validate(payload)


def test_scenario_rejects_duplicate_objective_ids() -> None:
    scenario = validate_document(
        ROOT / "examples/scenarios/boston-heat-transit.yaml", PolicyScenario
    )
    payload = scenario.model_dump(mode="json")
    payload["objectives"].append(payload["objectives"][0])
    with pytest.raises(ValidationError, match="objective ids must be unique"):
        PolicyScenario.model_validate(payload)


def test_intervention_rejects_optimized_as_input_evidence() -> None:
    scenario = validate_document(
        ROOT / "examples/scenarios/boston-heat-transit.yaml", PolicyScenario
    )
    payload = scenario.model_dump(mode="json")
    payload["interventions"][0]["evidence_type"] = "optimized"
    with pytest.raises(ValidationError, match="only be observed, proposed, or simulated"):
        PolicyScenario.model_validate(payload)
