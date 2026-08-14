"""Auditable bounded portfolio optimization with robust scenarios and negative releases."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from itertools import product
from math import fsum, isclose, prod

from pydantic import Field, field_validator, model_validator

from civicdecision.errors import AnalysisError
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    ensure_aware,
    normalize_float,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceType

PORTABLE_FLOAT_SIGNIFICANT_DIGITS = 12


def _portable(value: float) -> float:
    return normalize_float(value, significant_digits=PORTABLE_FLOAT_SIGNIFICANT_DIGITS)


class PortfolioRunStatus(StrEnum):
    OPTIMAL = "optimal"
    INFEASIBLE = "infeasible"
    SEARCH_LIMITED = "search-limited"


class ObjectiveStrategy(StrEnum):
    EXPECTED = "expected"
    WORST_CASE = "worst-case"


class ActionCandidate(StrictModel):
    action_id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: str = Field(min_length=1)
    max_units: int = Field(ge=0, le=100)
    unit_cost: float = Field(ge=0)
    unit_capacity: float = Field(ge=0)
    unit_risk: float = Field(ge=0)
    unit_benefit: float
    group_benefit_per_unit: dict[str, float] = Field(default_factory=dict)
    scenario_objective_per_unit: dict[str, float] = Field(min_length=1)
    input_evidence_type: EvidenceType
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("group_benefit_per_unit", "scenario_objective_per_unit")
    @classmethod
    def valid_mapping(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not key or not key.isascii() for key in value):
            raise ValueError("portfolio action mapping identifiers must be non-empty ASCII")
        return value

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("portfolio action source references must be unique")
        return value

    @field_validator("input_evidence_type")
    @classmethod
    def allowed_input_evidence(cls, value: EvidenceType) -> EvidenceType:
        if value not in {
            EvidenceType.ESTIMATED,
            EvidenceType.SIMULATED,
            EvidenceType.PROPOSED,
        }:
            raise ValueError("portfolio inputs must be estimated, simulated, or proposed")
        return value


class PortfolioConstraints(StrictModel):
    budget: float = Field(gt=0)
    capacity: float | None = Field(default=None, gt=0)
    maximum_risk: float | None = Field(default=None, ge=0)
    minimum_benefit: float | None = None
    minimum_group_benefit: dict[str, float] = Field(default_factory=dict)
    maximum_selected_actions: int | None = Field(default=None, ge=1)
    minimum_selected_actions: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def action_count_bounds(self) -> PortfolioConstraints:
        if (
            self.maximum_selected_actions is not None
            and self.minimum_selected_actions > self.maximum_selected_actions
        ):
            raise ValueError("minimum selected actions cannot exceed maximum")
        return self


class PortfolioConfig(StrictModel):
    objective_strategy: ObjectiveStrategy = ObjectiveStrategy.WORST_CASE
    scenario_weights: dict[str, float] = Field(default_factory=dict)
    maximum_evaluations: int = Field(default=1_000_000, ge=1, le=10_000_000)
    retained_plans: int = Field(default=500, ge=1, le=100_000)
    tolerance: float = Field(default=1e-9, gt=0, le=1e-3)

    @field_validator("scenario_weights")
    @classmethod
    def valid_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if any(item < 0 for item in value.values()):
            raise ValueError("scenario weights must be finite and nonnegative")
        return value


class PortfolioProblem(StrictModel):
    problem_id: str = Field(pattern=IDENTIFIER_PATTERN)
    objective: str = Field(min_length=1)
    objective_unit: str = Field(min_length=1)
    actions: list[ActionCandidate] = Field(min_length=1)
    constraints: PortfolioConstraints
    config: PortfolioConfig
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def problem_integrity(self) -> PortfolioProblem:
        action_ids = [item.action_id for item in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("portfolio action ids must be unique")
        scenario_sets = [set(item.scenario_objective_per_unit) for item in self.actions]
        if any(item != scenario_sets[0] for item in scenario_sets[1:]):
            raise ValueError("portfolio actions must share the same objective scenarios")
        scenarios = scenario_sets[0]
        if self.config.objective_strategy is ObjectiveStrategy.EXPECTED:
            if set(self.config.scenario_weights) != scenarios:
                raise ValueError("expected objective weights must exactly cover scenarios")
            total = sum(self.config.scenario_weights.values())
            if abs(total - 1) > self.config.tolerance:
                raise ValueError("expected objective scenario weights must sum to one")
        elif self.config.scenario_weights:
            raise ValueError("worst-case objectives cannot declare scenario weights")
        groups = set().union(*(item.group_benefit_per_unit for item in self.actions))
        if not set(self.constraints.minimum_group_benefit) <= groups:
            raise ValueError("portfolio group constraints must reference declared groups")
        return self


class ConstraintViolation(StrictModel):
    constraint_id: str = Field(pattern=IDENTIFIER_PATTERN)
    measured: float | int
    bound: float | int
    excess: float = Field(gt=0)
    details: str = Field(min_length=1)


class PortfolioPlan(StrictModel):
    plan_id: str = Field(pattern=IDENTIFIER_PATTERN)
    quantities: dict[str, int] = Field(min_length=1)
    total_cost: float = Field(ge=0)
    total_capacity: float = Field(ge=0)
    total_risk: float = Field(ge=0)
    total_benefit: float
    group_benefits: dict[str, float]
    scenario_objectives: dict[str, float] = Field(min_length=1)
    objective_value: float
    selected_action_count: int = Field(ge=0)
    feasible: bool
    violations: list[ConstraintViolation]
    binding_constraints: list[str]
    evidence_type: EvidenceType = EvidenceType.OPTIMIZED
    limitations: list[str] = Field(min_length=1)

    @field_validator("evidence_type")
    @classmethod
    def optimized_only(cls, value: EvidenceType) -> EvidenceType:
        if value is not EvidenceType.OPTIMIZED:
            raise ValueError("portfolio plans must retain optimized evidence type")
        return value

    @model_validator(mode="after")
    def feasibility_integrity(self) -> PortfolioPlan:
        if self.feasible == bool(self.violations):
            raise ValueError("portfolio plan feasibility must match its violation set")
        if self.selected_action_count != sum(quantity > 0 for quantity in self.quantities.values()):
            raise ValueError("selected action count must match positive quantities")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class SolverAudit(StrictModel):
    algorithm: str = Field(min_length=1)
    search_space_size: int = Field(ge=1)
    evaluated_plans: int = Field(ge=1)
    feasible_plans: int = Field(ge=0)
    retained_plans: int = Field(ge=1)
    enumeration_complete: bool
    theoretical_upper_bound: float
    incumbent_objective: float | None = None
    optimality_gap: float | None = Field(default=None, ge=0)
    tie_break_rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def audit_integrity(self) -> SolverAudit:
        if self.evaluated_plans > self.search_space_size:
            raise ValueError("evaluated plans cannot exceed search space")
        if self.feasible_plans > self.evaluated_plans:
            raise ValueError("feasible plans cannot exceed evaluated plans")
        if self.retained_plans > self.evaluated_plans:
            raise ValueError("retained plans cannot exceed evaluated plans")
        if self.enumeration_complete and self.evaluated_plans != self.search_space_size:
            raise ValueError("complete enumeration must cover the full search space")
        return self


class PortfolioOptimizationRun(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    status: PortfolioRunStatus
    evidence_type: EvidenceType = EvidenceType.OPTIMIZED
    problem: PortfolioProblem
    solver: SolverAudit
    baseline_plan: PortfolioPlan
    selected_plan_id: str | None = None
    selected_objective_change_from_baseline: float | None = None
    plans: list[PortfolioPlan] = Field(min_length=1)
    pareto_frontier_plan_ids: list[str]
    infeasibility_diagnostics: list[str]
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    failure_reason: str | None = None

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "portfolio run created_at")

    @field_validator("evidence_type")
    @classmethod
    def optimized_only(cls, value: EvidenceType) -> EvidenceType:
        if value is not EvidenceType.OPTIMIZED:
            raise ValueError("portfolio runs must retain optimized evidence type")
        return value

    @model_validator(mode="after")
    def run_integrity(self) -> PortfolioOptimizationRun:
        action_ids = {item.action_id for item in self.problem.actions}
        if set(self.baseline_plan.quantities) != action_ids or any(
            quantity != 0 for quantity in self.baseline_plan.quantities.values()
        ):
            raise ValueError("portfolio baseline must be the zero-action plan")
        ids = [item.plan_id for item in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("portfolio plan ids must be unique")
        known = set(ids)
        if not set(self.pareto_frontier_plan_ids) <= known:
            raise ValueError("Pareto frontier references must exist")
        if self.status is PortfolioRunStatus.OPTIMAL:
            if self.selected_plan_id is None or self.selected_plan_id not in known:
                raise ValueError("optimal runs require an existing selected plan")
            selected = next(item for item in self.plans if item.plan_id == self.selected_plan_id)
            if not selected.feasible:
                raise ValueError("optimal runs must select a feasible plan")
            if not self.solver.enumeration_complete or self.solver.optimality_gap != 0:
                raise ValueError("optimal status requires complete enumeration and zero gap")
            expected_change = selected.objective_value - self.baseline_plan.objective_value
            if self.selected_objective_change_from_baseline is None or not isclose(
                self.selected_objective_change_from_baseline,
                expected_change,
                rel_tol=0,
                abs_tol=self.problem.config.tolerance,
            ):
                raise ValueError(
                    "optimal runs require an exact selected objective change from baseline"
                )
            if self.failure_reason is not None:
                raise ValueError("optimal runs cannot have a failure reason")
        else:
            if self.selected_plan_id is not None:
                raise ValueError("negative optimization runs cannot select a plan")
            if not self.failure_reason:
                raise ValueError("negative optimization runs require a failure reason")
            if self.selected_objective_change_from_baseline is not None:
                raise ValueError("negative optimization runs cannot claim a baseline improvement")
            if (
                self.status is PortfolioRunStatus.INFEASIBLE
                and not self.solver.enumeration_complete
            ):
                raise ValueError("infeasibility requires complete enumeration")
            if (
                self.status is PortfolioRunStatus.SEARCH_LIMITED
                and self.solver.enumeration_complete
            ):
                raise ValueError("search-limited runs require incomplete enumeration")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


def _objective(scenario_values: dict[str, float], config: PortfolioConfig) -> float:
    if config.objective_strategy is ObjectiveStrategy.WORST_CASE:
        return min(scenario_values.values())
    return _portable(
        fsum(
            scenario_values[scenario] * weight
            for scenario, weight in config.scenario_weights.items()
        )
    )


def _evaluate(
    problem: PortfolioProblem,
    quantities: tuple[int, ...],
    index: int,
) -> PortfolioPlan:
    actions = problem.actions
    quantity_map = {
        action.action_id: quantity for action, quantity in zip(actions, quantities, strict=True)
    }
    total_cost = _portable(
        fsum(
            action.unit_cost * quantity
            for action, quantity in zip(actions, quantities, strict=True)
        )
    )
    total_capacity = _portable(
        fsum(
            action.unit_capacity * quantity
            for action, quantity in zip(actions, quantities, strict=True)
        )
    )
    total_risk = _portable(
        fsum(
            action.unit_risk * quantity
            for action, quantity in zip(actions, quantities, strict=True)
        )
    )
    total_benefit = _portable(
        fsum(
            action.unit_benefit * quantity
            for action, quantity in zip(actions, quantities, strict=True)
        )
    )
    group_ids = sorted(set().union(*(action.group_benefit_per_unit for action in actions)))
    group_benefits = {
        group: _portable(
            fsum(
                action.group_benefit_per_unit.get(group, 0) * quantity
                for action, quantity in zip(actions, quantities, strict=True)
            )
        )
        for group in group_ids
    }
    scenario_ids = sorted(actions[0].scenario_objective_per_unit)
    scenario_values = {
        scenario: _portable(
            fsum(
                action.scenario_objective_per_unit[scenario] * quantity
                for action, quantity in zip(actions, quantities, strict=True)
            )
        )
        for scenario in scenario_ids
    }
    selected_count = sum(quantity > 0 for quantity in quantities)
    constraints = problem.constraints
    tolerance = problem.config.tolerance
    violations = []

    def violation(
        identifier: str,
        measured: float | int,
        bound: float | int,
        excess: float,
        details: str,
    ) -> None:
        normalized_excess = _portable(float(excess))
        if normalized_excess > tolerance:
            violations.append(
                ConstraintViolation(
                    constraint_id=identifier,
                    measured=measured,
                    bound=bound,
                    excess=normalized_excess,
                    details=details,
                )
            )

    violation(
        "budget",
        total_cost,
        constraints.budget,
        total_cost - constraints.budget,
        "Total cost exceeds the declared budget.",
    )
    if constraints.capacity is not None:
        violation(
            "capacity",
            total_capacity,
            constraints.capacity,
            total_capacity - constraints.capacity,
            "Total capacity use exceeds availability.",
        )
    if constraints.maximum_risk is not None:
        violation(
            "maximum-risk",
            total_risk,
            constraints.maximum_risk,
            total_risk - constraints.maximum_risk,
            "Total modeled risk exceeds the cap.",
        )
    if constraints.minimum_benefit is not None:
        violation(
            "minimum-benefit",
            total_benefit,
            constraints.minimum_benefit,
            constraints.minimum_benefit - total_benefit,
            "Total modeled benefit is below the floor.",
        )
    for group, minimum in sorted(constraints.minimum_group_benefit.items()):
        violation(
            f"group-{group}",
            group_benefits[group],
            minimum,
            minimum - group_benefits[group],
            f"Modeled benefit for {group} is below its floor.",
        )
    if constraints.maximum_selected_actions is not None:
        violation(
            "maximum-selected-actions",
            selected_count,
            constraints.maximum_selected_actions,
            selected_count - constraints.maximum_selected_actions,
            "Too many action types are selected.",
        )
    violation(
        "minimum-selected-actions",
        selected_count,
        constraints.minimum_selected_actions,
        constraints.minimum_selected_actions - selected_count,
        "Too few action types are selected.",
    )
    binding: list[str] = []
    checks: list[tuple[str, float, float]] = [("budget", total_cost, constraints.budget)]
    if constraints.capacity is not None:
        checks.append(("capacity", total_capacity, constraints.capacity))
    if constraints.maximum_risk is not None:
        checks.append(("maximum-risk", total_risk, constraints.maximum_risk))
    if constraints.minimum_benefit is not None:
        checks.append(("minimum-benefit", total_benefit, constraints.minimum_benefit))
    checks.extend(
        (f"group-{group}", group_benefits[group], minimum)
        for group, minimum in sorted(constraints.minimum_group_benefit.items())
    )
    binding.extend(
        identifier for identifier, measured, bound in checks if abs(measured - bound) <= tolerance
    )
    return PortfolioPlan(
        plan_id=f"portfolio-plan-{index:08d}",
        quantities=quantity_map,
        total_cost=total_cost,
        total_capacity=total_capacity,
        total_risk=total_risk,
        total_benefit=total_benefit,
        group_benefits=group_benefits,
        scenario_objectives=scenario_values,
        objective_value=_objective(scenario_values, problem.config),
        selected_action_count=selected_count,
        feasible=not violations,
        violations=violations,
        binding_constraints=binding,
        limitations=[
            "Optimized values are mathematical outputs under declared inputs, not observed impact.",
            "Feasibility reflects only encoded constraints and does not establish "
            "implementability.",
        ],
    )


def _pareto_frontier(plans: list[PortfolioPlan], tolerance: float) -> list[str]:
    feasible = [item for item in plans if item.feasible]
    frontier = []
    for candidate in feasible:
        dominated = any(
            other.plan_id != candidate.plan_id
            and other.objective_value >= candidate.objective_value - tolerance
            and other.total_cost <= candidate.total_cost + tolerance
            and (
                other.objective_value > candidate.objective_value + tolerance
                or other.total_cost < candidate.total_cost - tolerance
            )
            for other in feasible
        )
        if not dominated:
            frontier.append(candidate.plan_id)
    return sorted(frontier)


def optimize_portfolio(
    *,
    run_id: str,
    problem: PortfolioProblem,
    created_at: datetime | None = None,
) -> PortfolioOptimizationRun:
    """Exhaustively enumerate a bounded portfolio problem under a deterministic evaluation cap."""

    search_space = prod(action.max_units + 1 for action in problem.actions)
    maximum = min(search_space, problem.config.maximum_evaluations)
    evaluated = []
    ranges = [range(action.max_units + 1) for action in problem.actions]
    for index, quantities in enumerate(product(*ranges)):
        if index >= maximum:
            break
        evaluated.append(_evaluate(problem, quantities, index))
    if not evaluated:
        raise AnalysisError("portfolio optimizer evaluated no plans")
    complete = len(evaluated) == search_space
    baseline = evaluated[0]
    feasible = [item for item in evaluated if item.feasible]
    ranked = sorted(
        evaluated,
        key=lambda item: (
            not item.feasible,
            -item.objective_value,
            item.total_cost,
            tuple(item.quantities.values()),
            item.plan_id,
        ),
    )
    retained = ranked[: min(problem.config.retained_plans, len(ranked))]
    retained_ids = {item.plan_id for item in retained}
    incumbent = (
        sorted(
            feasible,
            key=lambda item: (
                -item.objective_value,
                item.total_cost,
                tuple(item.quantities.values()),
                item.plan_id,
            ),
        )[0]
        if feasible
        else None
    )
    if incumbent is not None and incumbent.plan_id not in retained_ids:
        retained[-1] = incumbent
        retained_ids = {item.plan_id for item in retained}
    frontier_all = _pareto_frontier(evaluated, problem.config.tolerance)
    frontier = [identifier for identifier in frontier_all if identifier in retained_ids]
    theoretical_upper_bound = _portable(
        fsum(
            max(action.scenario_objective_per_unit.values()) * action.max_units
            for action in problem.actions
        )
    )
    if complete and incumbent is not None:
        status = PortfolioRunStatus.OPTIMAL
        selected_plan_id = incumbent.plan_id
        gap = 0.0
        failure_reason = None
    elif complete:
        status = PortfolioRunStatus.INFEASIBLE
        selected_plan_id = None
        gap = None
        failure_reason = "Complete enumeration found no plan satisfying every hard constraint."
    else:
        status = PortfolioRunStatus.SEARCH_LIMITED
        selected_plan_id = None
        gap = None
        failure_reason = (
            f"Stopped after deterministic evaluation limit {problem.config.maximum_evaluations} "
            f"of {search_space} plans; no optimality claim is issued."
        )
    violation_counts: dict[str, int] = {}
    for plan in evaluated:
        for violation in plan.violations:
            violation_counts[violation.constraint_id] = (
                violation_counts.get(violation.constraint_id, 0) + 1
            )
    return PortfolioOptimizationRun(
        run_id=run_id,
        created_at=created_at or datetime.now(UTC),
        status=status,
        problem=problem,
        solver=SolverAudit(
            algorithm="deterministic exhaustive integer enumeration",
            search_space_size=search_space,
            evaluated_plans=len(evaluated),
            feasible_plans=len(feasible),
            retained_plans=len(retained),
            enumeration_complete=complete,
            theoretical_upper_bound=theoretical_upper_bound,
            incumbent_objective=incumbent.objective_value if incumbent else None,
            optimality_gap=gap,
            tie_break_rule=(
                "Maximum robust/expected objective, then minimum cost, quantity tuple, stable ID."
            ),
        ),
        baseline_plan=baseline,
        selected_plan_id=selected_plan_id,
        selected_objective_change_from_baseline=(
            _portable(incumbent.objective_value - baseline.objective_value)
            if status is PortfolioRunStatus.OPTIMAL and incumbent is not None
            else None
        ),
        plans=retained,
        pareto_frontier_plan_ids=frontier,
        infeasibility_diagnostics=[
            f"{identifier}: violated by {count} of {len(evaluated)} evaluated plans"
            for identifier, count in sorted(violation_counts.items())
        ],
        diagnostics=[
            f"Evaluated {len(evaluated)} of {search_space} integer portfolios.",
            "Compared the selected objective with the explicitly serialized zero-action baseline.",
            f"Retained {len(retained)} ranked feasible/infeasible plans for audit.",
            f"Found {len(feasible)} feasible plans and {len(frontier_all)} Pareto-efficient plans.",
        ],
        limitations=[
            *problem.limitations,
            "Optimization proves only mathematical status for encoded actions, scenarios, and "
            "constraints.",
            "The theoretical upper bound ignores feasibility and is diagnostic, not a certified "
            "dual bound.",
            "Search-limited runs preserve incumbents but deliberately issue no selected "
            "recommendation.",
        ],
        failure_reason=failure_reason,
    )


__all__ = [
    "ActionCandidate",
    "ConstraintViolation",
    "ObjectiveStrategy",
    "PortfolioConfig",
    "PortfolioConstraints",
    "PortfolioOptimizationRun",
    "PortfolioPlan",
    "PortfolioProblem",
    "PortfolioRunStatus",
    "SolverAudit",
    "optimize_portfolio",
]
