from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from civicdecision.optimization import portfolio
from civicdecision.optimization.portfolio import (
    ActionCandidate,
    ObjectiveStrategy,
    PortfolioConfig,
    PortfolioConstraints,
    PortfolioOptimizationRun,
    PortfolioPlan,
    PortfolioProblem,
    PortfolioRunStatus,
    SolverAudit,
    optimize_portfolio,
)
from civicdecision.protocols.evidence import EvidenceType

CREATED = datetime(2025, 1, 1, tzinfo=UTC)


def action(
    identifier: str,
    *,
    max_units: int = 2,
    cost: float = 5,
    benefit: float = 5,
    risk: float = 1,
    group: float = 2,
    low: float = 3,
    high: float = 6,
) -> ActionCandidate:
    return ActionCandidate(
        action_id=identifier,
        label=f"Action {identifier}",
        max_units=max_units,
        unit_cost=cost,
        unit_capacity=1,
        unit_risk=risk,
        unit_benefit=benefit,
        group_benefit_per_unit={"priority": group},
        scenario_objective_per_unit={"low": low, "high": high},
        input_evidence_type=EvidenceType.SIMULATED,
        source_refs=[f"synthetic-fixture.{identifier}"],
        limitations=["Synthetic action is not an implementable intervention."],
    )


def problem(
    *,
    config: PortfolioConfig | None = None,
    constraints: PortfolioConstraints | None = None,
) -> PortfolioProblem:
    return PortfolioProblem(
        problem_id="synthetic.portfolio.qualification",
        objective="Maximize modeled benefit under the worst declared scenario.",
        objective_unit="benefit points",
        actions=[
            action("a", cost=5, benefit=6, risk=1, group=3, low=5, high=7),
            action("b", cost=4, benefit=4, risk=2, group=1, low=3, high=8),
            action("c", max_units=1, cost=7, benefit=9, risk=1, group=5, low=6, high=9),
        ],
        constraints=constraints
        or PortfolioConstraints(
            budget=14,
            capacity=3,
            maximum_risk=4,
            minimum_benefit=6,
            minimum_group_benefit={"priority": 3},
            maximum_selected_actions=2,
        ),
        config=config or PortfolioConfig(retained_plans=50),
        assumptions=["Additive synthetic action outcomes."],
        limitations=["Qualification optimization is not a policy recommendation."],
    )


def optimal_run() -> PortfolioOptimizationRun:
    return optimize_portfolio(
        run_id="optimization.portfolio.optimal",
        problem=problem(),
        created_at=CREATED,
    )


def test_complete_enumeration_proves_bounded_optimality() -> None:
    run = optimal_run()
    assert run.status is PortfolioRunStatus.OPTIMAL
    assert run.evidence_type is EvidenceType.OPTIMIZED
    assert run.solver.search_space_size == 18
    assert run.solver.evaluated_plans == 18
    assert run.solver.enumeration_complete
    assert run.solver.optimality_gap == 0
    assert all(quantity == 0 for quantity in run.baseline_plan.quantities.values())
    assert run.selected_plan_id
    selected = next(item for item in run.plans if item.plan_id == run.selected_plan_id)
    assert selected.feasible
    assert selected.total_cost <= run.problem.constraints.budget
    assert run.selected_objective_change_from_baseline == pytest.approx(
        selected.objective_value - run.baseline_plan.objective_value
    )
    assert run.content_hash() == optimal_run().content_hash()


def test_infeasible_run_preserves_constraint_diagnostics_and_no_selection() -> None:
    run = optimize_portfolio(
        run_id="optimization.portfolio.infeasible",
        problem=problem(
            constraints=PortfolioConstraints(
                budget=1,
                minimum_benefit=100,
                minimum_group_benefit={"priority": 100},
            )
        ),
        created_at=CREATED,
    )
    assert run.status is PortfolioRunStatus.INFEASIBLE
    assert run.selected_plan_id is None
    assert run.failure_reason
    assert run.selected_objective_change_from_baseline is None
    assert run.solver.enumeration_complete
    assert run.solver.feasible_plans == 0
    assert any("budget" in item for item in run.infeasibility_diagnostics)
    assert any(plan.violations for plan in run.plans)


def test_search_limited_run_withholds_optimality_and_selection() -> None:
    run = optimize_portfolio(
        run_id="optimization.portfolio.search-limited",
        problem=problem(config=PortfolioConfig(maximum_evaluations=4, retained_plans=4)),
        created_at=CREATED,
    )
    assert run.status is PortfolioRunStatus.SEARCH_LIMITED
    assert run.selected_plan_id is None
    assert not run.solver.enumeration_complete
    assert run.solver.evaluated_plans == 4
    assert run.failure_reason and "no optimality claim" in run.failure_reason
    assert run.selected_objective_change_from_baseline is None


def test_expected_objective_uses_declared_weights() -> None:
    run = optimize_portfolio(
        run_id="optimization.portfolio.expected",
        problem=problem(
            config=PortfolioConfig(
                objective_strategy=ObjectiveStrategy.EXPECTED,
                scenario_weights={"low": 0.25, "high": 0.75},
                retained_plans=50,
            )
        ),
        created_at=CREATED,
    )
    selected = next(item for item in run.plans if item.plan_id == run.selected_plan_id)
    assert selected.objective_value == pytest.approx(
        0.25 * selected.scenario_objectives["low"] + 0.75 * selected.scenario_objectives["high"]
    )


def test_every_evaluated_plan_is_retained_when_limit_allows() -> None:
    run = optimal_run()
    assert len(run.plans) == run.solver.search_space_size
    assert any(plan.feasible for plan in run.plans)
    assert any(not plan.feasible for plan in run.plans)
    assert set(run.pareto_frontier_plan_ids) <= {item.plan_id for item in run.plans}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(input_evidence_type="observed"),
            "estimated, simulated, or proposed",
        ),
        (
            lambda payload: payload.update(unit_cost=float("nan")),
            "finite number",
        ),
        (
            lambda payload: payload.update(source_refs=["a", "a"]),
            "references must be unique",
        ),
    ],
)
def test_action_contract_rejects_claim_and_numeric_drift(mutation: object, message: str) -> None:
    payload = action("a").model_dump()
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        ActionCandidate.model_validate(payload)

    payload = action("a").model_dump()
    payload["unit_benefit"] = float("inf")
    with pytest.raises(ValidationError, match="finite number"):
        ActionCandidate.model_validate(payload)
    payload = action("a").model_dump()
    payload["group_benefit_per_unit"] = {"priority": float("nan")}
    with pytest.raises(ValidationError, match="finite number"):
        ActionCandidate.model_validate(payload)
    payload = action("a").model_dump()
    payload["group_benefit_per_unit"] = {"优先": 1}
    with pytest.raises(ValidationError, match="non-empty ASCII"):
        ActionCandidate.model_validate(payload)


def test_problem_contract_requires_shared_scenarios_valid_groups_and_weights() -> None:
    payload = problem().model_dump()
    payload["actions"].append(payload["actions"][0])
    with pytest.raises(ValidationError, match="action ids must be unique"):
        PortfolioProblem.model_validate(payload)

    payload = problem().model_dump()
    payload["actions"][1]["scenario_objective_per_unit"] = {"other": 1}
    with pytest.raises(ValidationError, match="same objective scenarios"):
        PortfolioProblem.model_validate(payload)

    payload = problem().model_dump()
    payload["constraints"]["minimum_group_benefit"] = {"missing": 1}
    with pytest.raises(ValidationError, match="declared groups"):
        PortfolioProblem.model_validate(payload)

    with pytest.raises(ValidationError, match="exactly cover"):
        problem(
            config=PortfolioConfig(
                objective_strategy=ObjectiveStrategy.EXPECTED,
                scenario_weights={"low": 1},
            )
        )
    with pytest.raises(ValidationError, match="sum to one"):
        problem(
            config=PortfolioConfig(
                objective_strategy=ObjectiveStrategy.EXPECTED,
                scenario_weights={"low": 1, "high": 1},
            )
        )
    with pytest.raises(ValidationError, match="cannot declare scenario weights"):
        problem(config=PortfolioConfig(scenario_weights={"low": 0.5, "high": 0.5}))


def test_constraint_and_config_validation() -> None:
    with pytest.raises(ValidationError, match="cannot exceed maximum"):
        PortfolioConstraints(budget=1, minimum_selected_actions=3, maximum_selected_actions=2)
    with pytest.raises(ValidationError, match="finite number"):
        PortfolioConstraints(budget=float("inf"))
    with pytest.raises(ValidationError, match="finite and nonnegative"):
        PortfolioConfig(
            objective_strategy=ObjectiveStrategy.EXPECTED,
            scenario_weights={"low": -1},
        )
    with pytest.raises(ValidationError, match="finite number"):
        PortfolioConstraints(
            budget=1,
            minimum_group_benefit={"priority": float("nan")},
        )


def test_plan_and_solver_contracts_reject_internal_inconsistency() -> None:
    plan_payload = optimal_run().plans[0].model_dump(mode="json")
    plan_payload["evidence_type"] = "simulated"
    with pytest.raises(ValidationError, match="retain optimized"):
        PortfolioPlan.model_validate(plan_payload)

    plan_payload = optimal_run().plans[0].model_dump(mode="json")
    plan_payload["feasible"] = not plan_payload["feasible"]
    with pytest.raises(ValidationError, match="must match"):
        PortfolioPlan.model_validate(plan_payload)

    plan_payload = optimal_run().plans[0].model_dump(mode="json")
    plan_payload["selected_action_count"] += 1
    with pytest.raises(ValidationError, match="positive quantities"):
        PortfolioPlan.model_validate(plan_payload)

    audit = optimal_run().solver.model_dump()
    audit["evaluated_plans"] = audit["search_space_size"] + 1
    with pytest.raises(ValidationError, match="cannot exceed search space"):
        SolverAudit.model_validate(audit)
    audit = optimal_run().solver.model_dump()
    audit["feasible_plans"] = audit["evaluated_plans"] + 1
    with pytest.raises(ValidationError, match="cannot exceed evaluated"):
        SolverAudit.model_validate(audit)
    audit = optimal_run().solver.model_dump()
    audit["retained_plans"] = audit["evaluated_plans"] + 1
    with pytest.raises(ValidationError, match="retained plans cannot exceed"):
        SolverAudit.model_validate(audit)
    audit = optimal_run().solver.model_dump()
    audit["evaluated_plans"] -= 1
    audit["retained_plans"] = audit["evaluated_plans"]
    with pytest.raises(ValidationError, match="cover the full search space"):
        SolverAudit.model_validate(audit)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(evidence_type="simulated"),
            "retain optimized",
        ),
        (
            lambda payload: payload.update(selected_plan_id=None),
            "require an existing selected plan",
        ),
        (
            lambda payload: next(
                item for item in payload["plans"] if item["plan_id"] == payload["selected_plan_id"]
            ).update(
                feasible=False,
                violations=[
                    next(item for item in payload["plans"] if item["violations"])["violations"][0]
                ],
            ),
            "select a feasible plan",
        ),
        (
            lambda payload: payload["solver"].update(optimality_gap=0.1),
            "complete enumeration and zero gap",
        ),
        (
            lambda payload: payload["plans"].append(payload["plans"][0]),
            "plan ids must be unique",
        ),
        (
            lambda payload: payload["pareto_frontier_plan_ids"].append("missing"),
            "frontier references must exist",
        ),
        (
            lambda payload: payload.update(failure_reason="not allowed"),
            "cannot have a failure reason",
        ),
        (
            lambda payload: payload.update(selected_objective_change_from_baseline=999),
            "exact selected objective change from baseline",
        ),
    ],
)
def test_optimal_run_contract_rejects_status_and_reference_drift(
    mutation: object, message: str
) -> None:
    payload = optimal_run().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        PortfolioOptimizationRun.model_validate(payload)


def test_negative_run_contract_rejects_selection_or_missing_reason() -> None:
    run = optimize_portfolio(
        run_id="optimization.portfolio.negative-contract",
        problem=problem(config=PortfolioConfig(maximum_evaluations=1, retained_plans=1)),
        created_at=CREATED,
    )
    payload = run.model_dump(mode="json")
    payload["selected_plan_id"] = payload["plans"][0]["plan_id"]
    with pytest.raises(ValidationError, match="cannot select"):
        PortfolioOptimizationRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["failure_reason"] = None
    with pytest.raises(ValidationError, match="require a failure reason"):
        PortfolioOptimizationRun.model_validate(payload)

    payload = run.model_dump(mode="json")
    payload["selected_objective_change_from_baseline"] = 1
    with pytest.raises(ValidationError, match="cannot claim a baseline improvement"):
        PortfolioOptimizationRun.model_validate(payload)

    payload = run.model_dump(mode="json")
    payload["status"] = "infeasible"
    with pytest.raises(ValidationError, match="requires complete enumeration"):
        PortfolioOptimizationRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["solver"]["enumeration_complete"] = True
    payload["solver"]["evaluated_plans"] = payload["solver"]["search_space_size"]
    with pytest.raises(ValidationError, match="require incomplete enumeration"):
        PortfolioOptimizationRun.model_validate(payload)


def test_low_level_objective_and_retained_incumbent_branch() -> None:
    assert (
        portfolio._objective(
            {"a": 1, "b": 2}, PortfolioConfig(objective_strategy=ObjectiveStrategy.WORST_CASE)
        )
        == 1
    )
    assert (
        portfolio._objective(
            {"a": 1, "b": 2},
            PortfolioConfig(
                objective_strategy=ObjectiveStrategy.EXPECTED,
                scenario_weights={"a": 0.5, "b": 0.5},
            ),
        )
        == 1.5
    )
    run = optimize_portfolio(
        run_id="optimization.retained-incumbent",
        problem=problem(config=PortfolioConfig(retained_plans=1)),
        created_at=CREATED,
    )
    assert run.selected_plan_id == run.plans[0].plan_id


def test_run_contract_rejects_nonzero_or_incomplete_baseline() -> None:
    payload = optimal_run().model_dump(mode="json")
    payload["baseline_plan"]["quantities"]["a"] = 1
    payload["baseline_plan"]["selected_action_count"] = 1
    with pytest.raises(ValidationError, match="zero-action plan"):
        PortfolioOptimizationRun.model_validate(payload)

    payload = optimal_run().model_dump(mode="json")
    del payload["baseline_plan"]["quantities"]["a"]
    with pytest.raises(ValidationError, match="zero-action plan"):
        PortfolioOptimizationRun.model_validate(payload)
