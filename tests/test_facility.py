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
    select_robust_plan,
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


def test_access_standard_can_change_the_investment_choice() -> None:
    points = [point("a", 0, 0, 80, 10), point("b", 0, 0.001, 20, 5)]
    config = FacilityPlanningConfig(max_facilities=1, minimum_priority_coverage=0)
    geographic = enumerate_facility_plans(points, config)
    routes = {"a": {"a": 0, "b": 15}, "b": {"b": 0}}
    network = enumerate_facility_plans(points, config, travel_minutes=routes, minute_limit=15)
    assert [plan.covered_ids for plan in geographic] == [("a", "b"), ("a", "b")]
    assert [plan.covered_ids for plan in network] == [("a",), ("a", "b")]
    assert network[1].overall_coverage_rate == 1
    assert select_best_plan(network) == network[1]
    with pytest.raises(AnalysisError):
        enumerate_facility_plans(points, config, travel_minutes={"x": {}}, minute_limit=15)


def test_robust_choice_can_win_neither_period_and_must_satisfy_each_constraint() -> None:
    points = [point(x, 42, -71, 100, 50) for x in ("a", "b", "c")]
    plans = enumerate_facility_plans(points, FacilityPlanningConfig(max_facilities=1))

    def scored(values: list[float]):
        return [
            p.model_copy(update={"objective_score": v}) for p, v in zip(plans, values, strict=True)
        ]

    a, b = scored([1, 0.55, 0]), scored([0, 0.55, 1])
    choice = select_robust_plan({"am": a, "pm": b})
    assert choice and choice[0] == ("b",)
    assert choice[1]["am"] == pytest.approx(0.45)
    assert select_robust_plan({"am": a[:1], "pm": b[1:]}) is None
    with pytest.raises(AnalysisError):
        select_robust_plan({})


def test_departure_reliability_counts_the_same_origins_across_departures() -> None:
    from civicdecision.optimization.facility import rank_reliable_access

    pts = [point(k, 0, i, 1, 0) for i, k in enumerate(("a", "b", "c"))]
    config = FacilityPlanningConfig(max_facilities=1, minimum_priority_coverage=0)
    # Both sites cover two origins on average. Only site B serves its pair at both times.
    scenarios = {}
    for name, intermittent in [("first", "a"), ("second", "c")]:
        matrix: dict[str, dict[str, float]] = {p.id: {} for p in pts}
        for origin in [intermittent, "b"]:
            matrix[origin]["a"] = 5.0
        for origin in ["a", "b"]:
            matrix[origin]["b"] = 5.0
        scenarios[name] = enumerate_facility_plans(
            pts, config, travel_minutes=matrix, minute_limit=5
        )
    ranking = rank_reliable_access(pts, scenarios, required_departures=2)
    assert [r.selected_ids for r in ranking] == [("b",), ("a",), ("c",)]
    assert ranking[0].mean_need_share == ranking[1].mean_need_share
    assert ranking[1].reliable_ids == ("b",)
    assert ranking[1].departures_covered_by_origin == {"a": 1, "b": 2, "c": 1}
    assert rank_reliable_access(pts, {"empty": []}, required_departures=1) == []
    with pytest.raises(AnalysisError, match="scenario count"):
        rank_reliable_access(pts, scenarios, required_departures=3)
    with pytest.raises(AnalysisError, match="positive total"):
        rank_reliable_access([], scenarios, required_departures=1)
    with pytest.raises(AnalysisError, match="unambiguous"):
        rank_reliable_access(pts, {"": []}, required_departures=1)
    bogus = scenarios["first"][0].model_copy(update={"covered_ids": ("unknown",)})
    with pytest.raises(AnalysisError, match="known demand"):
        rank_reliable_access(pts, {"first": [bogus]}, required_departures=1)
