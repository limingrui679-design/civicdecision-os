from __future__ import annotations

import pytest
from pydantic import ValidationError

from civicdecision.analysis.spatial import haversine_km
from civicdecision.errors import AnalysisError
from civicdecision.optimization.facility import (
    DemandPoint,
    FacilityPlanningConfig,
    enumerate_facility_plans,
    select_best_plan,
)


def point(
    identifier: str,
    latitude: float,
    longitude: float,
    need: float,
    priority_rate: float,
) -> DemandPoint:
    return DemandPoint(
        id=identifier,
        latitude=latitude,
        longitude=longitude,
        population=100,
        estimated_need=need,
        priority_rate=priority_rate,
    )


def test_haversine_distance_has_explicit_kilometre_scale() -> None:
    assert haversine_km(42, -71, 42, -71) == 0
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.195, rel=1e-4)


def test_demand_point_rejects_need_above_population() -> None:
    with pytest.raises(ValidationError, match="cannot exceed population"):
        point("a", 0, 0, 101, 50)


def test_enumeration_retains_every_feasible_and_infeasible_plan() -> None:
    points = [
        point("a", 0, 0, 50, 50),
        point("b", 0, 0.005, 30, 30),
        point("c", 0, 0.03, 20, 20),
    ]
    config = FacilityPlanningConfig(
        max_facilities=2,
        facility_cost=10,
        budget=20,
        service_radius_km=1,
        minimum_priority_coverage=1,
        priority_group_share=0.34,
        cost_penalty=0.1,
    )
    plans = enumerate_facility_plans(points, config)
    assert len(plans) == 6
    assert any(plan.feasible for plan in plans)
    assert any(not plan.feasible for plan in plans)
    best = select_best_plan(plans)
    assert best is not None
    assert best.option_id.startswith("plan-")
    assert best.cost <= config.budget


def test_enumeration_input_gates_fail_safely() -> None:
    config = FacilityPlanningConfig()
    with pytest.raises(AnalysisError, match="at least one"):
        enumerate_facility_plans([], config)
    duplicate = [point("a", 0, 0, 1, 1), point("a", 1, 1, 1, 1)]
    with pytest.raises(AnalysisError, match="unique"):
        enumerate_facility_plans(duplicate, config)
    no_need = [point("a", 0, 0, 0, 1)]
    with pytest.raises(AnalysisError, match="positive estimated need"):
        enumerate_facility_plans(no_need, config)


def test_optimizer_returns_none_when_constraints_are_infeasible() -> None:
    plans = enumerate_facility_plans(
        [point("a", 0, 0, 10, 10), point("b", 10, 10, 10, 10)],
        FacilityPlanningConfig(
            max_facilities=1,
            facility_cost=10,
            budget=5,
            service_radius_km=0.1,
            minimum_priority_coverage=1,
        ),
    )
    assert select_best_plan(plans) is None


def test_zero_need_priority_group_uses_safe_coverage_denominator() -> None:
    plans = enumerate_facility_plans(
        [
            point("high-rate-zero-need", 0, 0, 0, 100),
            point("positive-need", 0, 0.001, 10, 1),
        ],
        FacilityPlanningConfig(
            max_facilities=1,
            facility_cost=10,
            budget=10,
            service_radius_km=1,
            minimum_priority_coverage=1,
            priority_group_share=0.5,
        ),
    )
    assert all(plan.priority_coverage_rate == 1 for plan in plans)
