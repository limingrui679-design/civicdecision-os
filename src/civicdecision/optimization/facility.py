"""Auditable exhaustive facility-location optimizer for bounded public samples."""

from __future__ import annotations

from itertools import combinations
from math import ceil

from pydantic import Field, model_validator

from civicdecision.analysis.spatial import haversine_km
from civicdecision.errors import AnalysisError
from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel


class DemandPoint(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    population: int = Field(ge=0)
    estimated_need: float = Field(ge=0)
    priority_rate: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def need_cannot_exceed_population(self) -> DemandPoint:
        if self.estimated_need > self.population:
            raise ValueError("estimated need cannot exceed population")
        return self


class FacilityPlanningConfig(StrictModel):
    max_facilities: int = Field(default=2, ge=1, le=10)
    facility_cost: float = Field(default=8000, gt=0)
    budget: float = Field(default=16000, gt=0)
    service_radius_km: float = Field(default=1.25, gt=0, le=100)
    minimum_priority_coverage: float = Field(default=0.60, ge=0, le=1)
    priority_group_share: float = Field(default=0.25, gt=0, le=1)
    cost_penalty: float = Field(default=0.15, ge=0, le=1)


class FacilityPlan(StrictModel):
    selected_ids: tuple[str, ...]
    covered_ids: tuple[str, ...]
    cost: float = Field(ge=0)
    estimated_need_covered: float = Field(ge=0)
    overall_coverage_rate: float = Field(ge=0, le=1)
    priority_coverage_rate: float = Field(ge=0, le=1)
    objective_score: float
    feasible: bool
    binding_constraints: list[str] = Field(default_factory=list)

    @property
    def option_id(self) -> str:
        return "plan-" + "-".join(self.selected_ids)


def _covered_points(
    points: list[DemandPoint], selected: tuple[DemandPoint, ...], radius_km: float
) -> tuple[DemandPoint, ...]:
    return tuple(
        point
        for point in points
        if any(
            haversine_km(
                point.latitude,
                point.longitude,
                facility.latitude,
                facility.longitude,
            )
            <= radius_km
            for facility in selected
        )
    )


def enumerate_facility_plans(
    points: list[DemandPoint], config: FacilityPlanningConfig
) -> list[FacilityPlan]:
    """Enumerate every bounded candidate combination and retain infeasible plans."""

    if not points:
        raise AnalysisError("facility optimization requires at least one demand point")
    ordered_points = sorted(points, key=lambda item: item.id)
    if len({point.id for point in ordered_points}) != len(ordered_points):
        raise AnalysisError("demand point ids must be unique")

    total_need = sum(point.estimated_need for point in ordered_points)
    if total_need <= 0:
        raise AnalysisError("facility optimization requires positive estimated need")
    priority_count = max(1, ceil(len(ordered_points) * config.priority_group_share))
    priority_points = sorted(
        ordered_points,
        key=lambda item: (-item.priority_rate, -item.estimated_need, item.id),
    )[:priority_count]
    priority_ids = {point.id for point in priority_points}
    total_priority_need = sum(point.estimated_need for point in priority_points)

    plans: list[FacilityPlan] = []
    maximum = min(config.max_facilities, len(ordered_points))
    for count in range(1, maximum + 1):
        for selected in combinations(ordered_points, count):
            covered = _covered_points(ordered_points, selected, config.service_radius_km)
            covered_ids = {point.id for point in covered}
            need_covered = sum(point.estimated_need for point in covered)
            priority_need_covered = sum(
                point.estimated_need for point in covered if point.id in priority_ids
            )
            cost = count * config.facility_cost
            overall_rate = need_covered / total_need
            priority_rate = (
                priority_need_covered / total_priority_need if total_priority_need else 1.0
            )
            feasible = cost <= config.budget and priority_rate >= config.minimum_priority_coverage
            binding: list[str] = []
            if abs(cost - config.budget) < 1e-9:
                binding.append("budget")
            if abs(priority_rate - config.minimum_priority_coverage) < 1e-9:
                binding.append("minimum-priority-coverage")
            score = overall_rate - config.cost_penalty * (cost / config.budget)
            plans.append(
                FacilityPlan(
                    selected_ids=tuple(point.id for point in selected),
                    covered_ids=tuple(sorted(covered_ids)),
                    cost=round(cost, 6),
                    estimated_need_covered=round(need_covered, 6),
                    overall_coverage_rate=round(overall_rate, 9),
                    priority_coverage_rate=round(priority_rate, 9),
                    objective_score=round(score, 9),
                    feasible=feasible,
                    binding_constraints=binding,
                )
            )
    return plans


def select_best_plan(plans: list[FacilityPlan]) -> FacilityPlan | None:
    """Return the deterministic best feasible plan or ``None``."""

    feasible = [plan for plan in plans if plan.feasible]
    if not feasible:
        return None
    return sorted(
        feasible,
        key=lambda plan: (
            -plan.objective_score,
            -plan.overall_coverage_rate,
            plan.cost,
            plan.selected_ids,
        ),
    )[0]
