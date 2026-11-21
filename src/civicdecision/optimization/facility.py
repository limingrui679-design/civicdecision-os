"""Auditable exhaustive facility-location optimizer for bounded public samples."""

from __future__ import annotations

from itertools import combinations
from math import ceil, isfinite

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


def _catchments(
    points: list[DemandPoint],
    radius: float,
    travel_minutes: dict[str, dict[str, float]] | None,
    minute_limit: float | None,
) -> dict[str, frozenset[str]]:
    """Index reachable residents once per candidate site, before plan enumeration."""
    if travel_minutes is None and minute_limit is None:
        neighbors: dict[str, set[str]] = {point.id: {point.id} for point in points}
        for a, b in combinations(points, 2):
            if haversine_km(a.latitude, a.longitude, b.latitude, b.longitude) <= radius:
                neighbors[a.id].add(b.id)
                neighbors[b.id].add(a.id)
        return {site: frozenset(ids) for site, ids in neighbors.items()}
    if (
        travel_minutes is None
        or minute_limit is None
        or not isfinite(minute_limit)
        or minute_limit < 0
    ):
        raise AnalysisError("provide a travel-time matrix and a finite nonnegative minute limit")
    ids = {point.id for point in points}
    if set(travel_minutes) - ids:
        raise AnalysisError("travel-time matrix contains an unknown origin")
    by_site: dict[str, set[str]] = {site: set() for site in ids}
    for origin, destinations in travel_minutes.items():
        for site, minutes in destinations.items():
            if site not in ids or not isfinite(minutes) or minutes < 0:
                raise AnalysisError("invalid travel-time destination or minutes")
            if minutes <= minute_limit:
                by_site[site].add(origin)
    return {site: frozenset(origins) for site, origins in by_site.items()}


def enumerate_facility_plans(
    points: list[DemandPoint],
    config: FacilityPlanningConfig,
    *,
    travel_minutes: dict[str, dict[str, float]] | None = None,
    minute_limit: float | None = None,
) -> list[FacilityPlan]:
    """Enumerate plans using a geographic radius or directed origin-to-site travel times.

    In travel-time mode only supplied routes with times within the limit count;
    provide explicit zero-minute routes for co-located origins where appropriate.
    """

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

    catchments = _catchments(ordered_points, config.service_radius_km, travel_minutes, minute_limit)
    plans: list[FacilityPlan] = []
    maximum = min(config.max_facilities, len(ordered_points))
    for count in range(1, maximum + 1):
        for selected in combinations(ordered_points, count):
            covered_ids = frozenset().union(*(catchments[site.id] for site in selected))
            covered = [point for point in ordered_points if point.id in covered_ids]
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


def select_robust_plan(
    scenarios: dict[str, list[FacilityPlan]],
) -> tuple[tuple[str, ...], dict[str, float]] | None:
    """Minimize worst loss against each scenario's best feasible plan, then mean loss and ID."""
    if not scenarios:
        raise AnalysisError("provide at least one planning scenario")
    regrets: dict[str, dict[tuple[str, ...], float]] = {}
    for name, plans in sorted(scenarios.items()):
        if not name or len({p.selected_ids for p in plans}) != len(plans):
            raise AnalysisError("scenario names and plan keys must be unambiguous")
        feasible = {p.selected_ids: p.objective_score for p in plans if p.feasible}
        if not feasible:
            return None
        best = max(feasible.values())
        regrets[name] = {ids: best - score for ids, score in feasible.items()}
    shared = set.intersection(*(set(result) for result in regrets.values()))
    if not shared:
        return None

    def ordering(ids: tuple[str, ...]) -> tuple[float, float, tuple[str, ...]]:
        losses = [result[ids] for result in regrets.values()]
        return max(losses), sum(losses), ids

    chosen = min(shared, key=ordering)
    return chosen, {name: results[chosen] for name, results in regrets.items()}


class ReliableAccessPlan(StrictModel):
    selected_ids: tuple[str, ...]
    observed_departures: int
    required_departures: int
    reliable_ids: tuple[str, ...]
    departures_covered_by_origin: dict[str, int]
    reliable_need_share: float
    mean_need_share: float


def rank_reliable_access(
    points: list[DemandPoint],
    scenarios: dict[str, list[FacilityPlan]],
    *,
    required_departures: int,
) -> list[ReliableAccessPlan]:
    """Rank fixed sites by the need of origins served on at least k departure times.

    Each equally weighted scenario represents one departure time. An unserved origin
    receives zero for that departure; the denominator includes every supplied origin.
    """
    if type(required_departures) is not int or not 1 <= required_departures <= len(scenarios):
        raise AnalysisError("required_departures must be between one and the scenario count")
    need = {point.id: point.estimated_need for point in points}
    total = sum(need.values())
    if len(need) != len(points) or total <= 0:
        raise AnalysisError("provide unique demand points with positive total need")

    indexed = []
    for name, plans in scenarios.items():
        if not name or len({plan.selected_ids for plan in plans}) != len(plans):
            raise AnalysisError("scenario names and plan keys must be unambiguous")
        snapshot = {}
        for plan in plans:
            served = set(plan.covered_ids)
            if not served <= need.keys() or len(served) != len(plan.covered_ids):
                raise AnalysisError("plan coverage must contain unique, known demand points")
            if plan.feasible:
                snapshot[plan.selected_ids] = served
        indexed.append(snapshot)

    ranking = []
    for sites in set.intersection(*(set(snapshot) for snapshot in indexed)):
        counts = dict.fromkeys(need, 0)
        for snapshot in indexed:
            for origin in snapshot[sites]:
                counts[origin] += 1
        reliable = tuple(sorted(origin for origin, k in counts.items() if k >= required_departures))
        ranking.append(
            ReliableAccessPlan(
                selected_ids=sites,
                observed_departures=len(indexed),
                required_departures=required_departures,
                reliable_ids=reliable,
                departures_covered_by_origin=counts,
                reliable_need_share=sum(need[origin] for origin in reliable) / total,
                mean_need_share=sum(need[origin] * k for origin, k in counts.items())
                / (len(indexed) * total),
            )
        )
    return sorted(
        ranking,
        key=lambda row: (-row.reliable_need_share, -row.mean_need_share, row.selected_ids),
    )
