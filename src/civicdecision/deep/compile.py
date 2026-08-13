"""Compile one local evidence binding into auditable Tier-D scenario artifacts."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import PurePosixPath
from statistics import fmean
from typing import cast
from zoneinfo import ZoneInfo

from civicdecision import __version__
from civicdecision.analysis.forecasting import (
    ForecastConfig,
    ForecastRun,
    TimeSeriesPoint,
    run_baseline_forecast,
)
from civicdecision.analysis.simulation import (
    DistributionKind,
    ParameterDistribution,
    SimulationConfig,
    SimulationModel,
    SimulationRun,
    SimulationTerm,
    ThresholdDirection,
    run_monte_carlo,
)
from civicdecision.analysis.uncertainty import (
    ObjectiveSense,
    OptionDraws,
    UncertaintyConfig,
    UncertaintyRun,
    analyze_option_uncertainty,
)
from civicdecision.connectors.municipal_service import MunicipalAggregation
from civicdecision.deep.load import LoadedDeepCity
from civicdecision.deep.models import (
    DeepScenarioPack,
    DeepScenarioStatus,
    DeepScenarioTemplate,
    ReadinessLevel,
    ScenarioArtifactRef,
    ScenarioCompletionStrategy,
)
from civicdecision.errors import AnalysisError
from civicdecision.optimization.portfolio import (
    ActionCandidate,
    ObjectiveStrategy,
    PortfolioConfig,
    PortfolioConstraints,
    PortfolioOptimizationRun,
    PortfolioPlan,
    PortfolioProblem,
    PortfolioRunStatus,
    optimize_portfolio,
)
from civicdecision.protocols.base import JsonValue, StrictModel, canonical_json, sha256_bytes
from civicdecision.protocols.decision import (
    DecisionOption,
    DecisionPack,
    Recommendation,
    Reproducibility,
    ReversalOutcome,
    ReversalTest,
    RunStatus,
    ValueOfInformation,
)
from civicdecision.protocols.evidence import EvidenceItem, EvidenceStatus, EvidenceType
from civicdecision.protocols.scenario import Constraint, Intervention, Objective, PolicyScenario


@dataclass(frozen=True)
class CompiledDeepScenario:
    pack: DeepScenarioPack
    artifact_bytes: dict[str, bytes]


def _seed(identifier: str) -> int:
    return int(hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8], 16)


def _model_bytes(model: StrictModel) -> bytes:
    return canonical_json(model) + b"\n"


def _scenario_id(city: LoadedDeepCity, template: DeepScenarioTemplate) -> str:
    return f"tierd.{city.spec.city_id}.{template.template_order:02d}"


def _data_cutoff(city: LoadedDeepCity) -> datetime:
    return datetime.combine(
        city.end_exclusive - timedelta(days=1),
        time.max,
        tzinfo=ZoneInfo(city.spec.timezone),
    )


def _policy_scenario(
    city: LoadedDeepCity,
    template: DeepScenarioTemplate,
    *,
    created_at: datetime,
    observed_request_count: int,
    daily_source_ref: str,
) -> PolicyScenario:
    scenario_id = _scenario_id(city, template)
    return PolicyScenario(
        scenario_id=scenario_id,
        title=f"{city.spec.display_name}: {template.title}",
        question=template.question,
        city_id=city.spec.city_id,
        as_of=created_at,
        data_cutoff=_data_cutoff(city),
        baseline=(
            f"The bounded reference input contains {observed_request_count:,} matching published "
            "service requests over 183 complete dates; it is workload evidence, not an outcome."
        ),
        interventions=[
            Intervention(
                id="triage-capacity",
                kind="planning-action",
                target="aggregate service-request workload",
                parameters={"maximum_units": 4, "effect_status": "hypothetical"},
            ),
            Intervention(
                id="surge-capacity",
                kind="planning-action",
                target="high-workload periods",
                parameters={"maximum_units": 4, "effect_status": "hypothetical"},
            ),
            Intervention(
                id="targeted-outreach",
                kind="planning-action",
                target="operational area-label coverage",
                parameters={"maximum_units": 4, "effect_status": "hypothetical"},
            ),
        ],
        objectives=[
            Objective(
                id="planning-benefit",
                metric="declared workload-response planning benefit",
                sense="maximize",
                weight=1.0,
                unit="planning-benefit index points",
            )
        ],
        constraints=[
            Constraint(
                id="bounded-budget",
                expression="abstract planning budget units <= 12",
                kind="budget",
                source_ref=daily_source_ref,
            ),
            Constraint(
                id="bounded-capacity",
                expression="declared capacity use <= 15",
                kind="capacity",
                source_ref=daily_source_ref,
            ),
            Constraint(
                id="claim-boundary",
                expression="no observed, causal, deployed, or impact claim from proposed effects",
                kind="regulatory",
                source_ref=daily_source_ref,
            ),
        ],
        analysis_modes=template.analysis_modes,
        evidence_requirements=template.evidence_requirements,
        random_seed=_seed(scenario_id),
        assumptions=template.assumptions,
        limitations=[*template.limitations, *template.prohibited_claims],
        tags=[template.suite.value, template.template_id, "tier-d", "public-data"],
    )


def _forecast(
    city: LoadedDeepCity,
    scenario: PolicyScenario,
    daily: dict[date, int],
    source_ref: str,
    created_at: datetime,
) -> ForecastRun:
    timezone = ZoneInfo(city.spec.timezone)
    points = [
        TimeSeriesPoint(
            timestamp=datetime.combine(day, time.min, tzinfo=timezone),
            value=float(value),
        )
        for day, value in daily.items()
    ]
    run = run_baseline_forecast(
        run_id=f"{scenario.scenario_id}.forecast",
        series_id=f"{scenario.scenario_id}.daily-demand",
        points=points,
        source_refs=[source_ref],
        config=ForecastConfig(
            horizon=14,
            backtest_folds=12,
            minimum_backtest_folds=5,
            minimum_train_size=28,
            moving_average_window=7,
            seasonal_period=7,
            interval_level=0.90,
        ),
        created_at=created_at,
    )
    absent_dates = sum(value == 0 for value in daily.values())
    if absent_dates:
        run.diagnostics.append(
            f"Zero-completed {absent_dates} dates absent from the endpoint-side aggregate."
        )
        run.limitations.append(
            "An absent aggregate date is encoded as zero for regular spacing, but the public "
            "source cannot distinguish true zero activity from delayed or incomplete publication."
        )
    return run


def _simulation(
    scenario: PolicyScenario,
    *,
    daily_mean: float,
    source_ref: str,
    created_at: datetime,
) -> SimulationRun:
    floor = max(daily_mean * 0.001, 0.001)
    parameters = [
        ParameterDistribution(
            parameter_id="baseline-demand",
            unit="requests/day",
            kind=DistributionKind.FIXED,
            evidence_type=EvidenceType.ESTIMATED,
            source_refs=[source_ref],
            fixed_value=daily_mean,
            assumptions=["The reference-window daily mean anchors this planning simulation."],
            limitations=["The historical mean is not a causal no-action counterfactual."],
        ),
        ParameterDistribution(
            parameter_id="demand-shock",
            unit="requests/day",
            kind=DistributionKind.TRIANGULAR,
            evidence_type=EvidenceType.PROPOSED,
            minimum=-0.10 * daily_mean,
            mode=0.03 * daily_mean,
            maximum=0.20 * daily_mean,
            assumptions=["The demand-shock range is a declared stress-test interval."],
            limitations=["The interval is not fitted to an intervention or hazard response."],
        ),
        ParameterDistribution(
            parameter_id="action-relief",
            unit="requests/day",
            kind=DistributionKind.TRIANGULAR,
            evidence_type=EvidenceType.PROPOSED,
            minimum=0.01 * daily_mean,
            mode=0.07 * daily_mean,
            maximum=0.18 * daily_mean,
            assumptions=["Relief is an illustrative planning parameter, not an effect estimate."],
            limitations=["No observed intervention identifies the action-relief distribution."],
        ),
        ParameterDistribution(
            parameter_id="implementation-friction",
            unit="requests/day",
            kind=DistributionKind.UNIFORM,
            evidence_type=EvidenceType.PROPOSED,
            minimum=0.0,
            maximum=max(0.06 * daily_mean, floor),
            assumptions=["Implementation friction offsets part of the hypothetical relief."],
            limitations=["No operational implementation sample calibrates this parameter."],
        ),
    ]
    model = SimulationModel(
        model_id=f"{scenario.scenario_id}.workload-model",
        scenario_ref=scenario.scenario_id,
        outcome_id="simulated-daily-workload",
        outcome_unit="requests/day",
        intercept=0,
        terms=[
            SimulationTerm(parameter_id="baseline-demand", coefficient=1),
            SimulationTerm(parameter_id="demand-shock", coefficient=1),
            SimulationTerm(parameter_id="action-relief", coefficient=-1),
            SimulationTerm(parameter_id="implementation-friction", coefficient=1),
        ],
        floor=0,
        method="Additive bounded workload stress model with declared hypothetical parameters.",
        assumptions=[
            "Parameter draws are independent and the additive form is used for transparent stress "
            "testing only."
        ],
        limitations=[
            "The model is not empirically calibrated to policy effects, operations, or causal "
            "outcomes."
        ],
    )
    return run_monte_carlo(
        run_id=f"{scenario.scenario_id}.simulation",
        model=model,
        parameters=parameters,
        config=SimulationConfig(
            iterations=2_500,
            random_seed=scenario.random_seed,
            retained_draws=50,
            threshold=daily_mean,
            threshold_direction=ThresholdDirection.AT_MOST,
        ),
        created_at=created_at,
    )


def _optimization(
    scenario: PolicyScenario,
    *,
    daily_mean: float,
    source_ref: str,
    created_at: datetime,
) -> PortfolioOptimizationRun:
    scale = max(1.0, daily_mean / 100.0)
    definitions = [
        ("triage-shift", "Cross-trained triage unit", 2.0, 1.4, 0.7, 1.00),
        ("surge-crew", "Time-bounded surge-capacity unit", 3.0, 2.1, 1.2, 1.35),
        ("digital-intake", "Intake-quality and deduplication unit", 1.5, 1.0, 0.5, 0.72),
        ("targeted-outreach", "Targeted access and outreach unit", 2.5, 1.2, 0.9, 0.88),
        ("reserve-capacity", "Contingency reserve unit", 2.2, 1.8, 0.8, 1.08),
    ]
    actions = [
        ActionCandidate(
            action_id=identifier,
            label=label,
            max_units=4,
            unit_cost=cost,
            unit_capacity=capacity,
            unit_risk=risk,
            unit_benefit=benefit * scale,
            group_benefit_per_unit={
                "area-balance": benefit
                * scale
                * (0.8 if identifier != "targeted-outreach" else 1.2)
            },
            scenario_objective_per_unit={
                "central": benefit * scale,
                "high-demand": benefit * scale * 0.72,
                "low-effect": benefit * scale * 0.55,
            },
            input_evidence_type=EvidenceType.PROPOSED,
            source_refs=[source_ref],
            limitations=[
                "Cost, capacity, risk, and benefit coefficients are transparent abstract planning "
                "inputs, not municipal estimates or observed effects."
            ],
        )
        for identifier, label, cost, capacity, risk, benefit in definitions
    ]
    problem = PortfolioProblem(
        problem_id=f"{scenario.scenario_id}.portfolio-problem",
        objective="maximize the worst-case declared planning-benefit index",
        objective_unit="planning-benefit index points",
        actions=actions,
        constraints=PortfolioConstraints(
            budget=12,
            capacity=15,
            maximum_risk=8,
            maximum_selected_actions=4,
            minimum_selected_actions=1,
        ),
        config=PortfolioConfig(
            objective_strategy=ObjectiveStrategy.WORST_CASE,
            maximum_evaluations=10_000,
            retained_plans=60,
        ),
        assumptions=[
            "Five generic planning actions are bounded at zero to four units and compared over "
            "three declared effectiveness states."
        ],
        limitations=[
            "The finite solver result is mathematically exact for encoded assumptions only and "
            "does not establish operational feasibility, cost, benefit, or impact."
        ],
    )
    return optimize_portfolio(
        run_id=f"{scenario.scenario_id}.optimization",
        problem=problem,
        created_at=created_at,
    )


def _uncertainty(
    scenario: PolicyScenario,
    optimization: PortfolioOptimizationRun,
    *,
    created_at: datetime,
) -> UncertaintyRun:
    if (
        optimization.status is not PortfolioRunStatus.OPTIMAL
        or optimization.selected_plan_id is None
    ):
        raise AnalysisError("completed Tier-D scenario requires an optimal bounded portfolio")
    generator = random.Random(scenario.random_seed + 17)
    values: dict[str, list[float]] = {
        "no-action": [],
        "conservative-plan": [],
        "bounded-portfolio": [],
    }
    for _ in range(1_000):
        common = generator.gauss(0.0, 0.04)
        values["no-action"].append(common + generator.gauss(0.0, 0.02))
        values["conservative-plan"].append(0.45 + common + generator.gauss(0.0, 0.08))
        values["bounded-portfolio"].append(1.00 + common + generator.gauss(0.0, 0.12))
    options = [
        OptionDraws(
            option_id=identifier,
            values=draws,
            source_refs=[optimization.run_id],
            evidence_type=EvidenceType.SIMULATED,
            limitations=[
                "Draw streams are declared comparative stress tests, not calibrated benefit or "
                "implementation outcomes."
            ],
        )
        for identifier, draws in values.items()
    ]
    return analyze_option_uncertainty(
        run_id=f"{scenario.scenario_id}.uncertainty",
        options=options,
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            confidence_level=0.95,
            practical_equivalence_margin=0.02,
            robust_probability_threshold=0.90,
            maximum_expected_regret=0.20,
            require_paired_draws=True,
        ),
        baseline_option_id="bounded-portfolio",
        created_at=created_at,
    )


def _selected_and_conservative(
    optimization: PortfolioOptimizationRun,
) -> tuple[PortfolioPlan, PortfolioPlan]:
    selected = next(
        item for item in optimization.plans if item.plan_id == optimization.selected_plan_id
    )
    feasible = [
        item for item in optimization.plans if item.feasible and item.plan_id != selected.plan_id
    ]
    if not feasible:
        raise AnalysisError("Tier-D optimizer retained no conservative feasible alternative")
    conservative = sorted(
        feasible,
        key=lambda item: (
            abs(item.objective_value - selected.objective_value * 0.55),
            item.total_cost,
            item.plan_id,
        ),
    )[0]
    return selected, conservative


def _voi() -> list[ValueOfInformation]:
    return [
        ValueOfInformation(
            id="local-action-effectiveness",
            uncertainty="The action-effect distributions are hypothetical.",
            decision_link="Calibrated effects can change objective rankings and reversal risk.",
            collection_action=(
                "Pre-register a prospective pilot or defensible quasi-experiment with outcome, "
                "comparison, timing, and diagnostic rules."
            ),
            priority_score=1.0,
            limitations=["This proposes future evidence; no causal pilot is claimed."],
        ),
        ValueOfInformation(
            id="operational-cost-capacity",
            uncertainty="Costs, staffing capacity, and implementation risk use abstract units.",
            decision_link="Verified constraints can remove options or change the selected plan.",
            collection_action=(
                "Obtain versioned local cost, staffing, procurement, service-level, and capacity "
                "records with responsible-owner review."
            ),
            priority_score=0.96,
            limitations=["No approved budget, procurement, or staffing commitment exists."],
        ),
        ValueOfInformation(
            id="distributional-outcomes",
            uncertainty="Operational area labels do not measure subgroup access or outcomes.",
            decision_link="Distributional evidence can reverse an apparently efficient portfolio.",
            collection_action=(
                "Define privacy-reviewed subgroup and neighborhood outcomes, reporting-access "
                "diagnostics, and an equity decision rule."
            ),
            priority_score=0.92,
            limitations=["Collection requires privacy, ethics, and representativeness review."],
        ),
    ]


def _decision_pack(
    city: LoadedDeepCity,
    template: DeepScenarioTemplate,
    scenario: PolicyScenario,
    *,
    observed_request_count: int,
    matching_category_count: int,
    forecast: ForecastRun,
    simulation: SimulationRun,
    optimization: PortfolioOptimizationRun,
    uncertainty: UncertaintyRun,
    created_at: datetime,
) -> DecisionPack:
    selected, conservative = _selected_and_conservative(optimization)
    summary_by_id = {item.option_id: item for item in uncertainty.option_summaries}

    def option(
        identifier: str,
        label: str,
        plan: PortfolioPlan | None,
        feasible: bool,
        evidence_type: EvidenceType,
    ) -> DecisionOption:
        uncertainty_summary = summary_by_id[identifier]
        return DecisionOption(
            id=identifier,
            label=label,
            evidence_type=evidence_type,
            feasible=feasible,
            metrics={
                "probability-best-under-declared-draws": uncertainty_summary.probability_best,
                "expected-regret-index": uncertainty_summary.expected_regret,
                "modeled-objective": plan.objective_value if plan else 0.0,
                "abstract-cost-units": plan.total_cost if plan else 0.0,
                "selected-action-types": plan.selected_action_count if plan else 0,
                "solver-plan-id": plan.plan_id if plan else "zero-action-baseline",
            },
            binding_constraints=plan.binding_constraints if plan else ["minimum-selected-actions"],
            limitations=[
                "Metrics are mathematical or simulated outputs under declared assumptions, not "
                "observed operational or social outcomes."
            ],
        )

    options = [
        option(
            "no-action",
            "Serialized zero-action comparator",
            None,
            False,
            EvidenceType.PROPOSED,
        ),
        option(
            "conservative-plan",
            "Lower-intensity retained feasible portfolio",
            conservative,
            True,
            EvidenceType.OPTIMIZED,
        ),
        option(
            "bounded-portfolio",
            "Worst-case-optimal bounded portfolio",
            selected,
            True,
            EvidenceType.OPTIMIZED,
        ),
    ]
    selected_option = uncertainty.selected_option_id
    if selected_option not in {item.id for item in options if item.feasible}:
        raise AnalysisError("Tier-D uncertainty selected an infeasible or unknown option")
    reversal_tests = [
        ReversalTest(
            id=f"paired-draw-{item.competing_option_id}",
            parameter="joint-parameter-draw",
            baseline_value="declared central assumptions",
            tested_value=item.reversal_probability,
            unit="reversal probability across paired draws",
            baseline_option_id=item.baseline_option_id,
            selected_option_id_after_test=(
                item.competing_option_id
                if item.reversal_probability > 0
                else item.baseline_option_id
            ),
            outcome=(
                ReversalOutcome.REVERSED
                if item.reversal_probability > 0
                else ReversalOutcome.STABLE
            ),
            evidence_type=EvidenceType.SIMULATED,
            method=item.condition,
            limitations=[
                "A simulated draw-level reversal is not evidence that a real-world decision will "
                "reverse or succeed."
            ],
        )
        for item in uncertainty.reversals
    ]
    daily_ref = city.municipal_manifests[MunicipalAggregation.DAILY_CATEGORY].artifact_id
    category_ref = city.municipal_manifests[MunicipalAggregation.CATEGORY_STATUS].artifact_id
    evidence = [
        EvidenceItem(
            id="observed-request-aggregate",
            type=EvidenceType.OBSERVED,
            status=EvidenceStatus.ESTABLISHED,
            title="Verified aggregate request workload",
            summary=(
                f"The declared focus rule matches {observed_request_count:,} requests across "
                f"{matching_category_count:,} public category labels."
            ),
            source_refs=[daily_ref, category_ref],
            limitations=[
                "Observed means present in verified aggregate public artifacts, not verified "
                "incidents, needs, service outcomes, or unique people."
            ],
        ),
        EvidenceItem(
            id="estimated-baseline-forecast",
            type=EvidenceType.ESTIMATED,
            status=EvidenceStatus.LIMITED,
            title="Transparent baseline workload forecast",
            summary=(
                "Rolling-origin selection chose "
                f"{forecast.selected_method.value if forecast.selected_method else 'none'} "
                f"for a {forecast.config.horizon}-day baseline forecast."
            ),
            source_refs=[daily_ref],
            method="Four transparent baselines compared on training-only rolling-origin folds.",
            diagnostics=forecast.diagnostics,
            limitations=forecast.limitations,
        ),
        EvidenceItem(
            id="simulated-workload-stress",
            type=EvidenceType.SIMULATED,
            status=EvidenceStatus.LIMITED,
            title="Seeded workload stress simulation",
            summary=(
                f"The engine generated {simulation.config.iterations:,} draws under declared "
                "uncalibrated action and demand assumptions."
            ),
            scenario_ref=scenario.scenario_id,
            diagnostics=simulation.diagnostics,
            assumptions=[
                item for parameter in simulation.parameters for item in parameter.assumptions
            ],
            limitations=simulation.limitations,
        ),
        EvidenceItem(
            id="optimized-bounded-portfolio",
            type=EvidenceType.OPTIMIZED,
            status=EvidenceStatus.LIMITED,
            title="Exhaustive bounded portfolio result",
            summary=(
                f"The solver evaluated {optimization.solver.evaluated_plans:,} of "
                f"{optimization.solver.search_space_size:,} portfolios and found "
                f"{optimization.solver.feasible_plans:,} feasible."
            ),
            objective=optimization.problem.objective,
            constraints=[
                "abstract budget <= 12",
                "declared capacity <= 15",
                "declared risk <= 8",
                "one to four action types",
            ],
            diagnostics=optimization.diagnostics,
            limitations=optimization.limitations,
        ),
        EvidenceItem(
            id="simulated-decision-uncertainty",
            type=EvidenceType.SIMULATED,
            status=EvidenceStatus.LIMITED,
            title="Paired option uncertainty and reversal analysis",
            summary=(
                f"Three options were compared over {uncertainty.option_summaries[0].draws:,} "
                "paired hypothetical benefit-index draws."
            ),
            scenario_ref=scenario.scenario_id,
            diagnostics=uncertainty.diagnostics,
            limitations=uncertainty.limitations,
        ),
        EvidenceItem(
            id="proposed-action-parameters",
            type=EvidenceType.PROPOSED,
            status=EvidenceStatus.LIMITED,
            title="Action coefficients remain proposals",
            summary=(
                "Costs, capacities, risks, effectiveness states, and implementation assumptions "
                "are transparent scenario inputs rather than measured local effects."
            ),
            limitations=[
                "No action is funded, approved, deployed, evaluated, or recommended for the city."
            ],
        ),
    ]
    voi = _voi()
    return DecisionPack(
        run_id=f"{scenario.scenario_id}.decision-pack",
        scenario_id=scenario.scenario_id,
        created_at=created_at,
        status=RunStatus.COMPLETED,
        source_manifests=city.source_manifests,
        evidence=evidence,
        options=options,
        recommendation=Recommendation(
            selected_option_id=selected_option,
            evidence_type=EvidenceType.OPTIMIZED,
            rationale=(
                "The selected option follows the deterministic paired-draw probability-best and "
                "regret rule after bounded optimization. It is planning-support output only, not "
                "a city recommendation, validated intervention, or impact claim."
            ),
            reversal_conditions=[item.condition for item in uncertainty.reversals],
            required_next_evidence=[item.collection_action for item in voi],
            limitations=[
                "Selection is conditional on public aggregate inputs and hypothetical action "
                "parameters; local owners must validate every operational and ethical premise."
            ],
        ),
        reversal_tests=reversal_tests,
        value_of_information=voi,
        reproducibility=Reproducibility(
            software_version=__version__,
            command=[
                "civicdecision",
                "deep",
                "build",
                "--source-directory",
                "examples/data/tier-d",
                "--output-directory",
                "catalog/deep-cities",
            ],
            random_seed=scenario.random_seed,
            environment={
                "python": ">=3.11",
                "algorithm": "deterministic-baselines-seeded-simulation-exhaustive-portfolio",
            },
            parameters={
                "scenario_template_id": template.template_id,
                "forecast_horizon": forecast.config.horizon,
                "simulation_iterations": simulation.config.iterations,
                "uncertainty_draws_per_option": uncertainty.option_summaries[0].draws,
                "optimization_search_space": optimization.solver.search_space_size,
            },
            source_hashes=[item.content_hash for item in city.source_manifests],
        ),
    )


def _negative_decision_pack(
    city: LoadedDeepCity,
    template: DeepScenarioTemplate,
    scenario: PolicyScenario,
    *,
    observed_request_count: int,
    failure_reason: str,
    created_at: datetime,
) -> DecisionPack:
    daily_ref = city.source_manifests[0].artifact_id
    evidence = [
        EvidenceItem(
            id="observed-aggregate-context",
            type=EvidenceType.OBSERVED,
            status=EvidenceStatus.LIMITED,
            title="Aggregate request context is available",
            summary=f"The bounded focus contains {observed_request_count:,} published requests.",
            source_refs=[daily_ref],
            limitations=[
                "Aggregate request context does not satisfy the scenario's missing evidence gate."
            ],
        )
    ]
    if template.completion_strategy is ScenarioCompletionStrategy.REQUIRED_CAUSAL_DESIGN:
        evidence.append(
            EvidenceItem(
                id="causal-identification-gate",
                type=EvidenceType.CAUSAL,
                status=EvidenceStatus.INSUFFICIENT,
                title="Causal identification is unavailable",
                summary=failure_reason,
                identification_strategy=(
                    "No valid strategy is issued because intervention timing, comparison groups, "
                    "outcome panels, and diagnostics are absent."
                ),
                diagnostics=[
                    "No dated intervention assignment.",
                    "No treated and comparison panel.",
                    "No pretrend, balance, placebo, or interference diagnostics.",
                ],
                limitations=[
                    "The scenario is released as insufficient evidence rather than an association "
                    "or causal estimate."
                ],
            )
        )
    else:
        evidence.append(
            EvidenceItem(
                id="required-input-gate",
                type=EvidenceType.PROPOSED,
                status=EvidenceStatus.INSUFFICIENT,
                title="Required analytical input is absent",
                summary=failure_reason,
                limitations=[
                    "No optimization or recommendation is emitted when a declared required input "
                    "is absent or the matching public workload is below its gate."
                ],
            )
        )
    next_evidence = (
        [
            "Bind intervention timing, a defensible comparison group, repeated outcome panel, and "
            "pre-registered identification diagnostics."
        ]
        if template.completion_strategy is ScenarioCompletionStrategy.REQUIRED_CAUSAL_DESIGN
        else [
            "Bind a versioned routable network or collect enough matching local source records, "
            "then rerun the declared evidence gate."
        ]
    )
    return DecisionPack(
        run_id=f"{scenario.scenario_id}.decision-pack",
        scenario_id=scenario.scenario_id,
        created_at=created_at,
        status=RunStatus.INSUFFICIENT_EVIDENCE,
        source_manifests=city.source_manifests,
        evidence=evidence,
        recommendation=Recommendation(
            evidence_type=EvidenceType.PROPOSED,
            rationale=(
                "The compiler withholds an option because the scenario's explicit evidence gate "
                "is not satisfied."
            ),
            required_next_evidence=next_evidence,
            limitations=[
                "No decision, effect, feasibility, deployment, or impact claim is issued."
            ],
        ),
        value_of_information=[
            ValueOfInformation(
                id="missing-required-evidence",
                uncertainty=failure_reason,
                decision_link="The missing evidence prevents a valid analytical selection.",
                collection_action=next_evidence[0],
                priority_score=1.0,
                limitations=["Priority is a governance gate, not a monetized EVPI calculation."],
            )
        ],
        failure_reason=failure_reason,
        reproducibility=Reproducibility(
            software_version=__version__,
            command=[
                "civicdecision",
                "deep",
                "build",
                "--source-directory",
                "examples/data/tier-d",
                "--output-directory",
                "catalog/deep-cities",
            ],
            random_seed=scenario.random_seed,
            environment={"python": ">=3.11", "algorithm": "evidence-gated-negative-release"},
            parameters={"scenario_template_id": template.template_id},
            source_hashes=[item.content_hash for item in city.source_manifests],
        ),
    )


def render_deep_decision_brief(
    city: LoadedDeepCity,
    template: DeepScenarioTemplate,
    pack: DecisionPack,
) -> str:
    lines = [
        f"# {city.spec.display_name} — {template.title}",
        "",
        f"- Scenario: `{pack.scenario_id}`",
        f"- Application suite: `{template.suite.value}`",
        f"- Status: `{pack.status.value}`",
        f"- DecisionPack content hash: `{pack.content_hash()}`",
        "",
        "## Claim boundary",
        "",
        template.intended_claim,
        "",
        "This artifact is a reproducible public-data planning exercise. It is not a deployed "
        "service, municipal recommendation, causal effect, observed intervention outcome, or "
        "evidence of adoption or real-world impact.",
        "",
        "## Result",
        "",
        pack.recommendation.rationale,
    ]
    if pack.failure_reason:
        lines.extend(["", f"Failure reason: {pack.failure_reason}"])
    selected = next(
        (item for item in pack.options if item.id == pack.recommendation.selected_option_id), None
    )
    if selected is not None:
        lines.extend(
            [
                "",
                f"Selected bounded planning option: `{selected.id}`",
                "",
                "| Metric | Value |",
                "|---|---:|",
                *(f"| {key} | {value} |" for key, value in selected.metrics.items()),
            ]
        )
    lines.extend(["", "## Evidence ledger", ""])
    lines.extend(
        f"- **{item.type.value} / {item.status.value}:** {item.summary}" for item in pack.evidence
    )
    lines.extend(["", "## Reversal diagnostics", ""])
    if pack.reversal_tests:
        lines.extend(
            f"- `{item.id}`: {item.outcome.value}; tested {item.parameter} = {item.tested_value}."
            for item in pack.reversal_tests
        )
    else:
        lines.append("- No option exists, so reversal testing is not applicable.")
    lines.extend(["", "## Required next evidence", ""])
    lines.extend(f"- {item}" for item in pack.recommendation.required_next_evidence)
    lines.extend(["", "## Reproduce", "", "```bash"])
    lines.append(" ".join(pack.reproducibility.command))
    lines.extend(["```", ""])
    return "\n".join(lines)


def compile_deep_scenario(
    city: LoadedDeepCity,
    template: DeepScenarioTemplate,
    *,
    created_at: datetime,
) -> CompiledDeepScenario:
    """Compile one of 96 city-bound scenarios and preserve negative evidence releases."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise AnalysisError("Tier-D compilation timestamp must be timezone aware")
    keywords = template.category_keywords or None
    daily = city.daily_request_counts(keywords)
    category_counts = city.category_request_counts(keywords)
    observed_request_count = sum(daily.values())
    category_total = sum(category_counts.values())
    if observed_request_count != category_total:
        raise AnalysisError(
            f"daily/category focus totals do not reconcile for {city.spec.city_id} and "
            f"{template.template_id}"
        )
    daily_ref = city.municipal_manifests[MunicipalAggregation.DAILY_CATEGORY].artifact_id
    scenario = _policy_scenario(
        city,
        template,
        created_at=created_at,
        observed_request_count=observed_request_count,
        daily_source_ref=daily_ref,
    )
    negative_reason: str | None = None
    if template.completion_strategy is ScenarioCompletionStrategy.REQUIRED_CAUSAL_DESIGN:
        negative_reason = (
            "The committed aggregate sources contain no dated intervention, comparison group, "
            "repeated outcome panel, or identification diagnostics."
        )
    elif template.completion_strategy is ScenarioCompletionStrategy.REQUIRED_NETWORK:
        negative_reason = (
            "The committed evidence contains no versioned routable network, service calendar, "
            "impedance validation, or real-time disruption state."
        )
    elif (
        template.completion_strategy is ScenarioCompletionStrategy.CATEGORY_DEMAND
        and observed_request_count < template.minimum_matching_requests
    ):
        negative_reason = (
            f"The declared keyword rule matches {observed_request_count:,} requests, below the "
            f"minimum gate of {template.minimum_matching_requests:,}."
        )

    pack_root = PurePosixPath("packs") / scenario.scenario_id
    artifact_bytes: dict[str, bytes] = {}
    scenario_path = (pack_root / "policy-scenario.json").as_posix()
    artifact_bytes[scenario_path] = _model_bytes(scenario)
    refs = [
        ScenarioArtifactRef(
            kind="policy-scenario",
            path=scenario_path,
            content_hash=sha256_bytes(artifact_bytes[scenario_path]),
            evidence_type=EvidenceType.PROPOSED,
        )
    ]
    forecast: ForecastRun | None = None
    simulation: SimulationRun | None = None
    optimization: PortfolioOptimizationRun | None = None
    uncertainty: UncertaintyRun | None = None
    if negative_reason is None:
        forecast = _forecast(city, scenario, daily, daily_ref, created_at)
        if forecast.status.value != "completed":
            raise AnalysisError(f"Tier-D forecast unexpectedly failed: {forecast.failure_reason}")
        daily_mean = fmean(daily.values())
        simulation = _simulation(
            scenario,
            daily_mean=daily_mean,
            source_ref=daily_ref,
            created_at=created_at,
        )
        optimization = _optimization(
            scenario,
            daily_mean=daily_mean,
            source_ref=daily_ref,
            created_at=created_at,
        )
        uncertainty = _uncertainty(scenario, optimization, created_at=created_at)
        for kind, name, model, evidence_type in [
            ("forecast-run", "forecast.json", forecast, EvidenceType.ESTIMATED),
            ("simulation-run", "simulation.json", simulation, EvidenceType.SIMULATED),
            ("optimization-run", "optimization.json", optimization, EvidenceType.OPTIMIZED),
            ("uncertainty-run", "uncertainty.json", uncertainty, EvidenceType.SIMULATED),
        ]:
            path = (pack_root / name).as_posix()
            artifact_bytes[path] = _model_bytes(model)
            refs.append(
                ScenarioArtifactRef(
                    kind=kind,  # type: ignore[arg-type]
                    path=path,
                    content_hash=sha256_bytes(artifact_bytes[path]),
                    evidence_type=evidence_type,
                )
            )
        decision = _decision_pack(
            city,
            template,
            scenario,
            observed_request_count=observed_request_count,
            matching_category_count=len(category_counts),
            forecast=forecast,
            simulation=simulation,
            optimization=optimization,
            uncertainty=uncertainty,
            created_at=created_at,
        )
        status = DeepScenarioStatus.COMPLETED
        readiness = ReadinessLevel.PLANNING_SUPPORT
        diagnostics = [
            f"Reconciled {observed_request_count:,} matching requests across independent views.",
            f"Forecast used {len(daily):,} regular daily observations.",
            f"Simulation generated {simulation.config.iterations:,} seeded draws.",
            f"Optimizer exhaustively evaluated {optimization.solver.evaluated_plans:,} plans.",
            f"Uncertainty compared {len(uncertainty.option_summaries):,} options over "
            f"{uncertainty.option_summaries[0].draws:,} paired draws.",
        ]
    else:
        decision = _negative_decision_pack(
            city,
            template,
            scenario,
            observed_request_count=observed_request_count,
            failure_reason=negative_reason,
            created_at=created_at,
        )
        status = DeepScenarioStatus.INSUFFICIENT_EVIDENCE
        readiness = ReadinessLevel.INSUFFICIENT_EVIDENCE
        diagnostics = [negative_reason, "No analytical option or recommendation was emitted."]
    decision_path = (pack_root / "decision-pack.json").as_posix()
    artifact_bytes[decision_path] = _model_bytes(decision)
    refs.append(
        ScenarioArtifactRef(
            kind="decision-pack",
            path=decision_path,
            content_hash=sha256_bytes(artifact_bytes[decision_path]),
            evidence_type=(
                EvidenceType.OPTIMIZED
                if status is DeepScenarioStatus.COMPLETED
                else EvidenceType.PROPOSED
            ),
        )
    )
    brief = render_deep_decision_brief(city, template, decision)
    brief_path = (pack_root / "decision-brief.md").as_posix()
    artifact_bytes[brief_path] = brief.encode("utf-8")
    refs.append(
        ScenarioArtifactRef(
            kind="decision-brief",
            path=brief_path,
            content_hash=sha256_bytes(artifact_bytes[brief_path]),
            evidence_type=(
                EvidenceType.OPTIMIZED
                if status is DeepScenarioStatus.COMPLETED
                else EvidenceType.PROPOSED
            ),
        )
    )
    top_categories = sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    pack = DeepScenarioPack(
        pack_id=scenario.scenario_id,
        city_id=city.spec.city_id,
        scenario_template_id=template.template_id,
        suite=template.suite,
        created_at=created_at.astimezone(UTC),
        data_cutoff=scenario.data_cutoff,
        status=status,
        readiness=readiness,
        scenario=scenario,
        source_refs=[item.artifact_id for item in city.source_manifests],
        observed_request_count=observed_request_count,
        observed_feature_summary={
            "reference_days": len(daily),
            "active_days": sum(value > 0 for value in daily.values()),
            "matching_category_labels": len(category_counts),
            "top_matching_categories": [
                {"category": category, "request_count": count} for category, count in top_categories
            ],
            "keyword_rule": cast(JsonValue, template.category_keywords),
            "minimum_matching_request_gate": template.minimum_matching_requests,
        },
        analytical_artifacts=refs,
        forecast=forecast,
        simulation=simulation,
        optimization=optimization,
        uncertainty=uncertainty,
        decision_pack=decision,
        decision_brief=brief,
        assumption_register=[
            *template.assumptions,
            "All action costs, capacities, risks, and effects are hypothetical planning inputs.",
            "Each city binding is one execution of a shared template, not a new method design.",
        ],
        diagnostics=diagnostics,
        limitations=[
            *template.limitations,
            *template.prohibited_claims,
            "Public data, internal reproducibility, and computational scale do not establish "
            "external review, adoption, deployment, users, or real-world impact.",
        ],
    )
    return CompiledDeepScenario(pack=pack, artifact_bytes=artifact_bytes)


__all__ = ["CompiledDeepScenario", "compile_deep_scenario", "render_deep_decision_brief"]
