"""Build deterministic engine qualification, public replay, and optimization artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from io import StringIO
from math import fsum, sqrt
from pathlib import Path
from statistics import fmean

from civicdecision.analysis.causal import (
    DifferenceInDifferencesConfig,
    DifferenceInDifferencesDesign,
    PanelObservation,
    run_difference_in_differences,
)
from civicdecision.analysis.forecasting import (
    ForecastConfig,
    ForecastStatus,
    TimeSeriesPoint,
    run_baseline_forecast,
)
from civicdecision.analysis.simulation import (
    DistributionKind,
    ParameterDistribution,
    SimulationConfig,
    SimulationModel,
    SimulationTerm,
    run_monte_carlo,
)
from civicdecision.analysis.uncertainty import (
    ObjectiveSense,
    OptionDraws,
    UncertaintyConfig,
    analyze_option_uncertainty,
)
from civicdecision.benchmarks.models import (
    BenchmarkArtifact,
    BenchmarkEvidenceSummary,
    BenchmarkRegistry,
    EngineQualificationEvidence,
    HistoricalReplay,
    HistoricalReplayEvidence,
    OptimizationTaskEvidence,
    ReplayStatus,
    artifact_set_hash,
)
from civicdecision.connectors.base import atomic_write
from civicdecision.errors import AnalysisError
from civicdecision.io import validate_document
from civicdecision.optimization.portfolio import (
    ActionCandidate,
    ObjectiveStrategy,
    PortfolioConfig,
    PortfolioConstraints,
    PortfolioOptimizationRun,
    PortfolioProblem,
    optimize_portfolio,
)
from civicdecision.protocols.base import StrictModel, normalize_float, sha256_file
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.source import SourceManifest
from civicdecision.standardized.models import StandardizedCityBundle, TierSRegistry


class BenchmarkBuildArtifacts(StrictModel):
    registry_path: Path
    evidence_summary_path: Path
    summary_csv_path: Path
    replay_evidence_csv_path: Path
    optimization_evidence_csv_path: Path
    qualification_evidence_csv_path: Path
    summary_markdown_path: Path
    checksum_path: Path
    artifact_paths: list[Path]


def _portable(value: float) -> float:
    return normalize_float(value, significant_digits=12)


def _write_model(path: Path, model: StrictModel) -> None:
    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    atomic_write(path, payload + b"\n")


def historical_replay_evidence(
    replay: HistoricalReplay, content_hash: str
) -> HistoricalReplayEvidence:
    """Project a completed replay into an independently recomputable evidence row."""

    if (
        replay.selected_method is None
        or replay.evaluation_mae is None
        or replay.evaluation_rmse is None
        or replay.empirical_interval_coverage is None
    ):
        raise AnalysisError(f"completed replay lacks evidence fields: {replay.replay_id}")
    return HistoricalReplayEvidence(
        replay_id=replay.replay_id,
        city_id=replay.city_id,
        city_name=replay.city_name,
        parameter=replay.parameter,
        source_artifact_id=replay.source_artifact_id,
        data_cutoff=replay.data_cutoff,
        evaluation_start=replay.evaluation_start,
        evaluation_end=replay.evaluation_end,
        training_observations=replay.forecast_run.observation_count,
        holdout_observations=len(replay.actual),
        selected_method=replay.selected_method,
        evaluation_mae=replay.evaluation_mae,
        evaluation_rmse=replay.evaluation_rmse,
        evaluation_wape=replay.evaluation_wape,
        empirical_interval_coverage=replay.empirical_interval_coverage,
        content_hash=content_hash,
    )


def optimization_task_evidence(
    run: PortfolioOptimizationRun, content_hash: str
) -> OptimizationTaskEvidence:
    """Project a solver run into an independently recomputable evidence row."""

    selected = (
        next(item for item in run.plans if item.plan_id == run.selected_plan_id)
        if run.selected_plan_id is not None
        else None
    )
    return OptimizationTaskEvidence(
        run_id=run.run_id,
        status=run.status,
        objective_strategy=run.problem.config.objective_strategy,
        search_space_size=run.solver.search_space_size,
        evaluated_plans=run.solver.evaluated_plans,
        feasible_plans=run.solver.feasible_plans,
        retained_plans=run.solver.retained_plans,
        enumeration_complete=run.solver.enumeration_complete,
        baseline_feasible=run.baseline_plan.feasible,
        baseline_objective=run.baseline_plan.objective_value,
        selected_plan_id=run.selected_plan_id,
        selected_objective=selected.objective_value if selected else None,
        selected_objective_change_from_baseline=run.selected_objective_change_from_baseline,
        pareto_frontier_plans=len(run.pareto_frontier_plan_ids),
        violated_constraint_ids=sorted(
            {violation.constraint_id for plan in run.plans for violation in plan.violations}
        ),
        content_hash=content_hash,
    )


def engine_qualification_evidence(
    *,
    artifact_id: str,
    run: StrictModel,
    source_refs: list[str],
    content_hash: str,
) -> EngineQualificationEvidence:
    """Project a typed qualification run into an independently recomputable evidence row."""

    payload = run.model_dump(mode="json")
    return EngineQualificationEvidence(
        artifact_id=artifact_id,
        run_id=str(payload["run_id"]),
        status=str(payload.get("status", "completed")),
        evidence_type=EvidenceType(str(payload["evidence_type"])),
        source_refs=list(dict.fromkeys(source_refs)),
        content_hash=content_hash,
    )


def _manifest_by_id(bundle: StandardizedCityBundle, source_id: str) -> SourceManifest:
    matching = [item for item in bundle.source_manifests if item.source_id == source_id]
    if len(matching) != 1:
        raise AnalysisError(f"expected one {source_id} manifest in {bundle.bundle_id}")
    return matching[0]


def _daily_points(artifact_path: Path, parameter: str) -> list[TimeSeriesPoint]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    try:
        raw = payload["properties"]["parameter"][parameter]
    except (KeyError, TypeError) as exc:
        raise AnalysisError(f"NASA POWER artifact lacks {parameter}: {artifact_path}") from exc
    if not isinstance(raw, dict):
        raise AnalysisError(f"NASA POWER {parameter} series must be an object")
    return [
        TimeSeriesPoint(
            timestamp=datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC),
            value=float(value),
        )
        for day, value in sorted(raw.items())
    ]


def _replay(
    *,
    bundle: StandardizedCityBundle,
    source_root: Path,
    parameter: str,
    horizon: int,
    ordinal: int,
) -> HistoricalReplay:
    manifest = _manifest_by_id(bundle, "nasa-power-daily-point")
    manifest_path = next(
        path
        for path in source_root.glob("*.manifest.json")
        if validate_document(path, SourceManifest).artifact_id == manifest.artifact_id
    )
    manifest.verify_artifact(manifest_path.parent)
    points = _daily_points(manifest_path.parent / manifest.artifact_path, parameter)
    train = points[:-horizon]
    actual_points = points[-horizon:]
    run = run_baseline_forecast(
        run_id=f"replay.forecast.{ordinal:03d}",
        series_id=f"{bundle.adapter.city_id}.{parameter.lower()}.2024",
        points=train,
        source_refs=[manifest.artifact_id],
        config=ForecastConfig(
            horizon=horizon,
            backtest_folds=8,
            minimum_backtest_folds=5,
            minimum_train_size=42,
            moving_average_window=7,
            seasonal_period=7,
            interval_level=0.90,
            require_nonnegative=parameter in {"PRECTOTCORR", "WS10M", "RH2M"},
        ),
        created_at=bundle.created_at,
    )
    if run.status is not ForecastStatus.COMPLETED or run.selected_method is None:
        raise AnalysisError(f"historical replay forecast failed for {bundle.adapter.city_id}")
    actual = [item.value for item in actual_points]
    predicted = [item.point for item in run.forecast]
    errors = [
        prediction - observation for observation, prediction in zip(actual, predicted, strict=True)
    ]
    absolute = [abs(value) for value in errors]
    denominator = fsum(abs(item) for item in actual)
    coverage = (
        sum(
            forecast.lower <= observation <= forecast.upper
            for observation, forecast in zip(actual, run.forecast, strict=True)
        )
        / horizon
    )
    return HistoricalReplay(
        replay_id=f"historical-replay-{ordinal:03d}",
        created_at=bundle.created_at,
        city_id=bundle.adapter.city_id,
        city_name=bundle.adapter.display_name,
        source_artifact_id=manifest.artifact_id,
        source_content_hash=manifest.content_hash,
        parameter=parameter,
        train_start=train[0].timestamp,
        data_cutoff=train[-1].timestamp,
        evaluation_start=actual_points[0].timestamp,
        evaluation_end=actual_points[-1].timestamp,
        actual=actual,
        forecast_run=run,
        selected_method=run.selected_method,
        evaluation_mae=_portable(fmean(absolute)),
        evaluation_rmse=_portable(sqrt(fmean(value * value for value in errors))),
        evaluation_wape=_portable(fsum(absolute) / denominator) if denominator else None,
        empirical_interval_coverage=_portable(coverage),
        status=ReplayStatus.COMPLETED,
        diagnostics=[
            f"Training uses {len(train)} observations ending before the {horizon}-day holdout.",
            "Method selection uses only rolling-origin folds inside the training window.",
            "The committed actual holdout is compared only after the forecast is compiled.",
        ],
        limitations=[
            "This is a historical public-data replay, not a live forecast or production service.",
            "One gridded point does not represent municipal exposure or intervention outcomes.",
            "Forty replay records are repeated tasks over 20 source artifacts and two parameters, "
            "not 40 independent cities or studies.",
        ],
    )


def _optimization_problem(index: int) -> PortfolioProblem:
    variant = index % 10
    actions = [
        ActionCandidate(
            action_id=f"action-{letter}",
            label=f"Synthetic benchmark action {letter}",
            max_units=2 + ((index + offset) % 3),
            unit_cost=float(3 + offset + variant % 3),
            unit_capacity=float(1 + offset % 2),
            unit_risk=float(1 + (index + offset) % 4),
            unit_benefit=float(4 + offset * 2 + variant),
            group_benefit_per_unit={
                "priority": float(2 + offset),
                "general": float(3 + variant % 2 + offset),
            },
            scenario_objective_per_unit={
                "adverse": float(2 + offset + variant * 0.2),
                "base": float(4 + 2 * offset + variant * 0.3),
                "favorable": float(6 + 3 * offset + variant * 0.4),
            },
            input_evidence_type=EvidenceType.PROPOSED,
            source_refs=[f"synthetic-qualification.portfolio-family-{variant}"],
            limitations=["Qualification action is synthetic and not implementable."],
        )
        for offset, letter in enumerate("abcd")
    ]
    kind = index % 10
    if kind in {7, 8}:
        constraints = PortfolioConstraints(
            budget=1,
            minimum_benefit=1_000,
            minimum_group_benefit={"priority": 500},
        )
    else:
        constraints = PortfolioConstraints(
            budget=float(18 + variant * 2),
            capacity=float(8 + variant),
            maximum_risk=float(12 + variant),
            minimum_benefit=float(5 + variant),
            minimum_group_benefit={"priority": float(3 + variant % 4)},
            maximum_selected_actions=3,
        )
    portfolio_strategy = ObjectiveStrategy.EXPECTED if index % 2 else ObjectiveStrategy.WORST_CASE
    config = PortfolioConfig(
        objective_strategy=portfolio_strategy,
        scenario_weights=(
            {"adverse": 0.25, "base": 0.5, "favorable": 0.25}
            if portfolio_strategy is ObjectiveStrategy.EXPECTED
            else {}
        ),
        maximum_evaluations=5 if kind == 9 else 1_000_000,
        retained_plans=75,
    )
    return PortfolioProblem(
        problem_id=f"synthetic.portfolio.task-{index:03d}",
        objective="Maximize modeled portfolio benefit across three declared stress scenarios.",
        objective_unit="synthetic benefit points",
        actions=actions,
        constraints=constraints,
        config=config,
        assumptions=["Action quantities and modeled benefits are additive."],
        limitations=[
            "This is a deterministic synthetic qualification task, not a real city recommendation.",
            "Repeated task families vary parameters and statuses but are not independent field "
            "studies.",
        ],
    )


def _qualification_runs(created_at: datetime) -> list[tuple[str, StrictModel, list[str], str]]:
    causal_design = DifferenceInDifferencesDesign(
        study_id="synthetic.did.milestone-4",
        estimand="Synthetic average treatment effect on treated units in two post periods.",
        treatment_definition="Additive fixture shift at period 4.",
        comparison_definition="Never-treated fixture units.",
        assignment_mechanism="Deterministic fixture assignment by ID prefix.",
        no_anticipation_rationale="No shift is applied before period 4.",
        parallel_trends_rationale="Both fixture groups have identical pre-period slopes.",
        no_interference_rationale="Fixture unit outcomes are generated independently.",
        source_refs=["synthetic-qualification.did-panel"],
        limitations=["Synthetic identification evidence is not a real policy study."],
    )
    panel = [
        PanelObservation(
            unit_id=f"{'treated' if treated else 'comparison'}-{unit}",
            period=period,
            outcome=10 + unit * 0.4 + period + (3 if treated and period >= 4 else 0),
            treated_group=treated,
        )
        for treated in (False, True)
        for unit in range(6)
        for period in range(6)
    ]
    causal_pass = run_difference_in_differences(
        run_id="qualification.causal.passed",
        design=causal_design,
        observations=panel,
        config=DifferenceInDifferencesConfig(
            intervention_period=4,
            minimum_units_per_group=5,
            minimum_pre_periods=4,
            minimum_post_periods=2,
            pretrend_slope_equivalence_margin=0.2,
            placebo_effect_equivalence_margin=0.5,
        ),
        created_at=created_at,
    )
    causal_fail_panel = [
        item.model_copy(
            update={
                "outcome": item.outcome
                + (item.period if item.treated_group and item.period < 4 else 0)
            }
        )
        for item in panel
    ]
    causal_fail = run_difference_in_differences(
        run_id="qualification.causal.failed-pretrend",
        design=causal_design,
        observations=causal_fail_panel,
        config=DifferenceInDifferencesConfig(
            intervention_period=4,
            minimum_units_per_group=5,
            minimum_pre_periods=4,
            minimum_post_periods=2,
            pretrend_slope_equivalence_margin=0.2,
            placebo_effect_equivalence_margin=0.5,
        ),
        created_at=created_at,
    )
    simulation_model = SimulationModel(
        model_id="synthetic.risk.milestone-4",
        scenario_ref="synthetic.risk-scenario.milestone-4",
        outcome_id="synthetic-risk-score",
        outcome_unit="points",
        intercept=5,
        terms=[
            SimulationTerm(parameter_id="exposure", coefficient=2),
            SimulationTerm(parameter_id="protection", coefficient=-3),
            SimulationTerm(parameter_id="shock", coefficient=10),
        ],
        floor=0,
        ceiling=100,
        method="Bounded linear qualification model.",
        assumptions=["Independent fixture draws."],
        limitations=["Synthetic model is not calibrated to a real city."],
    )
    simulation_parameters = [
        ParameterDistribution(
            parameter_id="exposure",
            unit="points",
            kind=DistributionKind.UNIFORM,
            evidence_type=EvidenceType.ESTIMATED,
            source_refs=["synthetic-qualification.exposure"],
            minimum=0,
            maximum=10,
            assumptions=["Uniform fixture."],
            limitations=["Synthetic input."],
        ),
        ParameterDistribution(
            parameter_id="protection",
            unit="points",
            kind=DistributionKind.TRIANGULAR,
            evidence_type=EvidenceType.PROPOSED,
            minimum=0,
            mode=2,
            maximum=5,
            assumptions=["Triangular fixture."],
            limitations=["Synthetic input."],
        ),
        ParameterDistribution(
            parameter_id="shock",
            unit="indicator",
            kind=DistributionKind.BERNOULLI,
            evidence_type=EvidenceType.PROPOSED,
            probability=0.2,
            assumptions=["Independent shock fixture."],
            limitations=["Synthetic input."],
        ),
    ]
    simulation_run = run_monte_carlo(
        run_id="qualification.simulation.seeded",
        model=simulation_model,
        parameters=simulation_parameters,
        config=SimulationConfig(
            iterations=10_000,
            random_seed=20260812,
            retained_draws=25,
            threshold=20,
        ),
        created_at=created_at,
    )
    uncertainty_robust = analyze_option_uncertainty(
        run_id="qualification.uncertainty.robust",
        options=[
            OptionDraws(
                option_id="a",
                values=[10, 11, 12, 13, 14],
                source_refs=["synthetic-qualification.option-a"],
                evidence_type=EvidenceType.SIMULATED,
                limitations=["Synthetic option."],
            ),
            OptionDraws(
                option_id="b",
                values=[5, 6, 7, 8, 9],
                source_refs=["synthetic-qualification.option-b"],
                evidence_type=EvidenceType.SIMULATED,
                limitations=["Synthetic option."],
            ),
        ],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            robust_probability_threshold=0.9,
            maximum_expected_regret=0,
        ),
        created_at=created_at,
    )
    uncertainty_reversal = analyze_option_uncertainty(
        run_id="qualification.uncertainty.reversal",
        options=[
            OptionDraws(
                option_id="incumbent",
                values=[10, 2, 10, 2],
                source_refs=["synthetic-qualification.incumbent"],
                evidence_type=EvidenceType.ESTIMATED,
                limitations=["Synthetic option."],
            ),
            OptionDraws(
                option_id="competitor",
                values=[2, 10, 2, 10],
                source_refs=["synthetic-qualification.competitor"],
                evidence_type=EvidenceType.ESTIMATED,
                limitations=["Synthetic option."],
            ),
        ],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            robust_probability_threshold=0.75,
        ),
        baseline_option_id="incumbent",
        created_at=created_at,
    )
    return [
        (
            "qualification-causal-passed",
            causal_pass,
            ["synthetic-qualification.did-panel"],
            "Synthetic method qualification; not a real causal study.",
        ),
        (
            "qualification-causal-failed-pretrend",
            causal_fail,
            ["synthetic-qualification.did-panel"],
            "Negative synthetic identification result preserved as estimated association.",
        ),
        (
            "qualification-simulation-seeded",
            simulation_run,
            [
                item
                for parameter in simulation_parameters
                for item in (parameter.source_refs or ["proposed"])
            ],
            "Seeded synthetic simulation; not observed impact.",
        ),
        (
            "qualification-uncertainty-robust",
            uncertainty_robust,
            ["synthetic-qualification.option-a", "synthetic-qualification.option-b"],
            "Synthetic robustness qualification; not probability of policy success.",
        ),
        (
            "qualification-uncertainty-reversal",
            uncertainty_reversal,
            ["synthetic-qualification.incumbent", "synthetic-qualification.competitor"],
            "Synthetic reversal qualification; not field evidence.",
        ),
    ]


def build_milestone_4_benchmarks(
    *,
    standardized_directory: Path,
    nasa_source_directory: Path,
    output_directory: Path,
    replay_city_count: int = 20,
    optimization_task_count: int = 100,
) -> BenchmarkBuildArtifacts:
    """Build 40 held-out public replays, 100 optimizer tasks, and engine qualification runs."""

    if replay_city_count < 1 or optimization_task_count < 1:
        raise AnalysisError("benchmark target counts must be positive")
    registry = validate_document(standardized_directory / "registry.json", TierSRegistry)
    if replay_city_count > len(registry.entries):
        raise AnalysisError("benchmark replay city target exceeds Tier-S coverage")
    output_directory.mkdir(parents=True, exist_ok=True)
    artifacts: list[BenchmarkArtifact] = []
    replay_evidence: list[HistoricalReplayEvidence] = []
    optimization_evidence: list[OptimizationTaskEvidence] = []
    qualification_evidence: list[EngineQualificationEvidence] = []
    written: list[Path] = []
    status_counts: Counter[str] = Counter()
    ordinal = 0
    for entry in registry.entries[:replay_city_count]:
        bundle = validate_document(
            standardized_directory / entry.bundle_ref, StandardizedCityBundle
        )
        for parameter in ("T2M", "PRECTOTCORR"):
            ordinal += 1
            replay = _replay(
                bundle=bundle,
                source_root=nasa_source_directory,
                parameter=parameter,
                horizon=30,
                ordinal=ordinal,
            )
            relative = Path("historical-replays") / f"{replay.replay_id}.json"
            path = output_directory / relative
            _write_model(path, replay)
            written.append(path)
            status_counts[replay.status.value] += 1
            artifacts.append(
                BenchmarkArtifact(
                    artifact_id=replay.replay_id,
                    kind="historical-replay",
                    relative_path=relative.as_posix(),
                    content_hash=sha256_file(path),
                    status=replay.status.value,
                    source_refs=[replay.source_artifact_id],
                    evidence_boundary=(
                        "Held-out 2024 public gridded-point replay; estimated forecast evidence, "
                        "not live performance, city exposure, or intervention impact."
                    ),
                )
            )
            replay_evidence.append(historical_replay_evidence(replay, sha256_file(path)))
    for index in range(1, optimization_task_count + 1):
        run = optimize_portfolio(
            run_id=f"optimization.portfolio.task-{index:03d}",
            problem=_optimization_problem(index),
            created_at=registry.created_at,
        )
        relative = Path("optimization-tasks") / f"{run.run_id}.json"
        path = output_directory / relative
        _write_model(path, run)
        written.append(path)
        status_counts[run.status.value] += 1
        artifacts.append(
            BenchmarkArtifact(
                artifact_id=run.run_id,
                kind="optimization-task",
                relative_path=relative.as_posix(),
                content_hash=sha256_file(path),
                status=run.status.value,
                source_refs=list(
                    dict.fromkeys(
                        source for action in run.problem.actions for source in action.source_refs
                    )
                ),
                evidence_boundary=(
                    "Synthetic solver qualification; optimized mathematical output, not a real "
                    "action portfolio, implementation, or observed benefit."
                ),
            )
        )
        optimization_evidence.append(optimization_task_evidence(run, sha256_file(path)))
    qualification = _qualification_runs(registry.created_at)
    for identifier, qualification_run, source_refs, boundary in qualification:
        relative = Path("engine-qualification") / f"{identifier}.json"
        path = output_directory / relative
        _write_model(path, qualification_run)
        written.append(path)
        status = str(qualification_run.model_dump(mode="json").get("status", "completed"))
        status_counts[status] += 1
        artifacts.append(
            BenchmarkArtifact(
                artifact_id=identifier,
                kind="engine-qualification",
                relative_path=relative.as_posix(),
                content_hash=sha256_file(path),
                status=status,
                source_refs=list(dict.fromkeys(source_refs)),
                evidence_boundary=boundary,
            )
        )
        qualification_evidence.append(
            engine_qualification_evidence(
                artifact_id=identifier,
                run=qualification_run,
                source_refs=list(dict.fromkeys(source_refs)),
                content_hash=sha256_file(path),
            )
        )
    run_hashes = {item.artifact_id: item.content_hash for item in artifacts}
    method_counts = dict(
        sorted(Counter(item.selected_method.value for item in replay_evidence).items())
    )
    parameter_counts = dict(sorted(Counter(item.parameter for item in replay_evidence).items()))
    optimization_status_counts = dict(
        sorted(Counter(item.status.value for item in optimization_evidence).items())
    )
    optimization_strategy_counts = dict(
        sorted(Counter(item.objective_strategy.value for item in optimization_evidence).items())
    )
    evidence_summary = BenchmarkEvidenceSummary(
        summary_id="milestone-4-analytical-engine-evidence.v1",
        created_at=registry.created_at,
        artifact_set_hash=artifact_set_hash(run_hashes),
        run_artifact_hashes=run_hashes,
        historical_replays=replay_evidence,
        optimization_tasks=optimization_evidence,
        engine_qualification_runs=qualification_evidence,
        method_counts=method_counts,
        parameter_counts=parameter_counts,
        optimization_status_counts=optimization_status_counts,
        optimization_strategy_counts=optimization_strategy_counts,
        total_search_space_size=sum(item.search_space_size for item in optimization_evidence),
        total_evaluated_plans=sum(item.evaluated_plans for item in optimization_evidence),
        total_feasible_plans=sum(item.feasible_plans for item in optimization_evidence),
        baseline_comparisons=sum(
            item.selected_objective_change_from_baseline is not None
            for item in optimization_evidence
        ),
        limitations=[
            "Replay metrics summarize held-out public point-series tasks, not live service-level "
            "performance.",
            "Optimization totals summarize synthetic finite search spaces and cannot be treated "
            "as real interventions or benefits.",
            "Qualification rows establish typed engine behavior, not external validity or impact.",
        ],
    )
    evidence_summary_path = output_directory / "evidence-summary.json"
    _write_model(evidence_summary_path, evidence_summary)
    written.append(evidence_summary_path)
    benchmark_registry = BenchmarkRegistry(
        registry_id="milestone-4-analytical-engine-benchmarks.v1",
        created_at=registry.created_at,
        artifacts=artifacts,
        historical_replays=ordinal,
        optimization_tasks=optimization_task_count,
        engine_qualification_runs=len(qualification),
        status_counts=dict(sorted(status_counts.items())),
        evidence_summary_ref=evidence_summary_path.relative_to(output_directory).as_posix(),
        evidence_summary_content_hash=sha256_file(evidence_summary_path),
        artifact_set_hash=evidence_summary.artifact_set_hash,
        limitations=[
            "Historical replays use real committed public NASA POWER data but remain point-level "
            "method evaluations, not production forecasts.",
            "Optimization and engine-qualification artifacts are synthetic and prove software "
            "behavior only.",
            "Artifact counts distinguish tasks from unique sources, cities, methods, and real "
            "studies.",
        ],
    )
    registry_path = output_directory / "registry.json"
    _write_model(registry_path, benchmark_registry)
    written.append(registry_path)
    summary_csv_path = output_directory / "summary.csv"
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["artifact_id", "kind", "status", "relative_path", "content_hash"])
    for artifact in artifacts:
        writer.writerow(
            [
                artifact.artifact_id,
                artifact.kind,
                artifact.status,
                artifact.relative_path,
                artifact.content_hash,
            ]
        )
    atomic_write(summary_csv_path, buffer.getvalue().encode("utf-8"))
    written.append(summary_csv_path)
    replay_evidence_csv_path = output_directory / "historical-replay-evidence.csv"
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "replay_id",
            "city_id",
            "city_name",
            "parameter",
            "source_artifact_id",
            "training_observations",
            "holdout_observations",
            "selected_method",
            "evaluation_mae",
            "evaluation_rmse",
            "evaluation_wape",
            "empirical_interval_coverage",
            "data_cutoff",
            "evaluation_start",
            "evaluation_end",
            "content_hash",
        ]
    )
    for replay_row in replay_evidence:
        writer.writerow(
            [
                replay_row.replay_id,
                replay_row.city_id,
                replay_row.city_name,
                replay_row.parameter,
                replay_row.source_artifact_id,
                replay_row.training_observations,
                replay_row.holdout_observations,
                replay_row.selected_method.value,
                replay_row.evaluation_mae,
                replay_row.evaluation_rmse,
                replay_row.evaluation_wape,
                replay_row.empirical_interval_coverage,
                replay_row.data_cutoff.isoformat(),
                replay_row.evaluation_start.isoformat(),
                replay_row.evaluation_end.isoformat(),
                replay_row.content_hash,
            ]
        )
    atomic_write(replay_evidence_csv_path, buffer.getvalue().encode("utf-8"))
    written.append(replay_evidence_csv_path)
    optimization_evidence_csv_path = output_directory / "optimization-task-evidence.csv"
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "run_id",
            "status",
            "objective_strategy",
            "search_space_size",
            "evaluated_plans",
            "feasible_plans",
            "retained_plans",
            "enumeration_complete",
            "baseline_feasible",
            "baseline_objective",
            "selected_plan_id",
            "selected_objective",
            "selected_objective_change_from_baseline",
            "pareto_frontier_plans",
            "violated_constraint_ids",
            "content_hash",
        ]
    )
    for optimization_row in optimization_evidence:
        writer.writerow(
            [
                optimization_row.run_id,
                optimization_row.status.value,
                optimization_row.objective_strategy.value,
                optimization_row.search_space_size,
                optimization_row.evaluated_plans,
                optimization_row.feasible_plans,
                optimization_row.retained_plans,
                optimization_row.enumeration_complete,
                optimization_row.baseline_feasible,
                optimization_row.baseline_objective,
                optimization_row.selected_plan_id,
                optimization_row.selected_objective,
                optimization_row.selected_objective_change_from_baseline,
                optimization_row.pareto_frontier_plans,
                ";".join(optimization_row.violated_constraint_ids),
                optimization_row.content_hash,
            ]
        )
    atomic_write(optimization_evidence_csv_path, buffer.getvalue().encode("utf-8"))
    written.append(optimization_evidence_csv_path)
    qualification_evidence_csv_path = output_directory / "qualification-evidence.csv"
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "artifact_id",
            "run_id",
            "status",
            "evidence_type",
            "source_refs",
            "content_hash",
        ]
    )
    for qualification_row in qualification_evidence:
        writer.writerow(
            [
                qualification_row.artifact_id,
                qualification_row.run_id,
                qualification_row.status,
                qualification_row.evidence_type.value,
                ";".join(qualification_row.source_refs),
                qualification_row.content_hash,
            ]
        )
    atomic_write(qualification_evidence_csv_path, buffer.getvalue().encode("utf-8"))
    written.append(qualification_evidence_csv_path)
    summary_markdown_path = output_directory / "summary.md"
    markdown = "\n".join(
        [
            "# Milestone 4 analytical-engine benchmark audit",
            "",
            f"Registry content hash: `{benchmark_registry.content_hash()}`",
            "",
            f"- Historical held-out public-data replays: {ordinal}",
            f"- Synthetic portfolio optimization tasks: {optimization_task_count}",
            f"- Synthetic engine qualification runs: {len(qualification)}",
            f"- Total independently serialized run artifacts: {len(artifacts)}",
            f"- Training observations across replay tasks: "
            f"{sum(item.training_observations for item in replay_evidence):,}",
            f"- Strictly held-out observations across replay tasks: "
            f"{sum(item.holdout_observations for item in replay_evidence):,}",
            f"- Optimization search-space portfolios declared: "
            f"{evidence_summary.total_search_space_size:,}",
            f"- Optimization portfolios actually evaluated: "
            f"{evidence_summary.total_evaluated_plans:,}",
            f"- Feasible portfolios encountered: {evidence_summary.total_feasible_plans:,}",
            f"- Explicit selected-versus-zero-action baseline comparisons: "
            f"{evidence_summary.baseline_comparisons}",
            "",
            "## Forecast method counts",
            "",
            *[f"- `{method}`: {count}" for method, count in method_counts.items()],
            "",
            "## Optimization strategy counts",
            "",
            *[
                f"- `{strategy}`: {count}"
                for strategy, count in optimization_strategy_counts.items()
            ],
            "",
            "## Status counts",
            "",
            *[f"- `{status}`: {count}" for status, count in sorted(status_counts.items())],
            "",
            "## Claim boundary",
            "",
            "The 40 historical replays are held-out tasks over 20 NASA POWER city-point artifacts "
            "and two parameters. They are not 40 cities, 40 independent datasets, or live "
            "forecasts. The 100 optimization tasks and five method-qualification runs are "
            "synthetic software evidence. They do not establish external validity, adoption, "
            "users, or impact.",
            "",
        ]
    )
    atomic_write(summary_markdown_path, markdown.encode("utf-8"))
    written.append(summary_markdown_path)
    checksum_path = output_directory / "SHA256SUMS"
    checksum_lines = [
        f"{sha256_file(path)[7:]}  {path.relative_to(output_directory).as_posix()}"
        for path in written
    ]
    atomic_write(checksum_path, ("\n".join(checksum_lines) + "\n").encode("ascii"))
    return BenchmarkBuildArtifacts(
        registry_path=registry_path,
        evidence_summary_path=evidence_summary_path,
        summary_csv_path=summary_csv_path,
        replay_evidence_csv_path=replay_evidence_csv_path,
        optimization_evidence_csv_path=optimization_evidence_csv_path,
        qualification_evidence_csv_path=qualification_evidence_csv_path,
        summary_markdown_path=summary_markdown_path,
        checksum_path=checksum_path,
        artifact_paths=[output_directory / item.relative_path for item in artifacts],
    )


__all__ = [
    "BenchmarkBuildArtifacts",
    "build_milestone_4_benchmarks",
    "engine_qualification_evidence",
    "historical_replay_evidence",
    "optimization_task_evidence",
]
