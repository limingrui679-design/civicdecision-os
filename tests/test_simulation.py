from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from civicdecision.analysis import simulation
from civicdecision.analysis.simulation import (
    DistributionKind,
    ParameterDistribution,
    SimulationConfig,
    SimulationModel,
    SimulationRun,
    SimulationStatus,
    SimulationTerm,
    ThresholdDirection,
    run_monte_carlo,
)
from civicdecision.errors import AnalysisError
from civicdecision.protocols.evidence import EvidenceType

CREATED = datetime(2025, 1, 1, tzinfo=UTC)


def parameter(
    identifier: str,
    kind: DistributionKind,
    **kwargs: object,
) -> ParameterDistribution:
    return ParameterDistribution(
        parameter_id=identifier,
        unit="unit",
        kind=kind,
        evidence_type=EvidenceType.ESTIMATED,
        source_refs=[f"synthetic-fixture.{identifier}"],
        assumptions=["Qualification fixture assumption."],
        limitations=["Synthetic parameter is not real-world evidence."],
        **kwargs,
    )


def model() -> SimulationModel:
    return SimulationModel(
        model_id="synthetic.linear-risk.v1",
        scenario_ref="synthetic.risk-scenario.v1",
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
        assumptions=["Parameter draws are independent."],
        limitations=["The qualification model is not calibrated to a real city."],
    )


def parameters() -> list[ParameterDistribution]:
    return [
        parameter("exposure", DistributionKind.UNIFORM, minimum=0, maximum=10),
        parameter(
            "protection",
            DistributionKind.TRIANGULAR,
            minimum=0,
            mode=2,
            maximum=5,
        ),
        parameter("shock", DistributionKind.BERNOULLI, probability=0.2),
    ]


def completed_run() -> SimulationRun:
    return run_monte_carlo(
        run_id="simulation.synthetic.qualification",
        model=model(),
        parameters=parameters(),
        config=SimulationConfig(
            iterations=1000,
            random_seed=42,
            retained_draws=10,
            threshold=20,
            threshold_direction=ThresholdDirection.AT_LEAST,
        ),
        created_at=CREATED,
    )


def test_seeded_monte_carlo_is_reproducible_and_typed_simulated() -> None:
    first = completed_run()
    second = completed_run()
    assert first.status is SimulationStatus.COMPLETED
    assert first.evidence_type is EvidenceType.SIMULATED
    assert first.content_hash() == second.content_hash()
    assert first.draw_stream_hash == second.draw_stream_hash
    assert first.summary == second.summary
    assert len(first.retained_draws) == 10
    assert first.summary is not None
    assert 0 <= (first.summary.threshold_probability or 0) <= 1
    portable_config = SimulationConfig(
        iterations=100,
        random_seed=42,
        retained_draws=10,
        portable_float_significant_digits=12,
    )
    portable_first = run_monte_carlo(
        run_id="simulation.synthetic.portable",
        model=model(),
        parameters=parameters(),
        config=portable_config,
        created_at=CREATED,
    )
    portable_second = run_monte_carlo(
        run_id="simulation.synthetic.portable",
        model=model(),
        parameters=parameters(),
        config=portable_config,
        created_at=CREATED,
    )
    assert portable_first.draw_stream_hash == portable_second.draw_stream_hash
    assert portable_first.retained_draws[0].parameters["exposure"] == float(
        format(portable_first.retained_draws[0].parameters["exposure"], ".12g")
    )


def test_sensitivity_ranks_cover_every_parameter_without_causal_language() -> None:
    run = completed_run()
    assert {item.parameter_id for item in run.sensitivity} == {
        "exposure",
        "protection",
        "shock",
    }
    assert {item.absolute_rank for item in run.sensitivity} == {1, 2, 3}
    assert all(-1 <= item.pearson_correlation <= 1 for item in run.sensitivity)
    assert any("not causal" in item for item in run.diagnostics)


def test_all_distribution_kinds_sample_and_model_bounds_apply() -> None:
    varied = [
        parameter("fixed", DistributionKind.FIXED, fixed_value=2),
        parameter(
            "normal", DistributionKind.NORMAL, mean=0, standard_deviation=3, minimum=-1, maximum=1
        ),
        parameter("empirical", DistributionKind.EMPIRICAL, empirical_values=[1, 2, 3]),
    ]
    bounded = SimulationModel(
        model_id="synthetic.bounds.v1",
        scenario_ref="synthetic.bounds-scenario.v1",
        outcome_id="bounded-outcome",
        outcome_unit="points",
        intercept=0,
        terms=[SimulationTerm(parameter_id=item.parameter_id, coefficient=100) for item in varied],
        floor=0,
        ceiling=10,
        method="Bounded qualification model.",
        assumptions=["Independent fixture draws."],
        limitations=["Synthetic only."],
    )
    run = run_monte_carlo(
        run_id="simulation.distributions.qualification",
        model=bounded,
        parameters=varied,
        config=SimulationConfig(
            iterations=100,
            random_seed=1,
            retained_draws=100,
            threshold=5,
            threshold_direction=ThresholdDirection.AT_MOST,
        ),
        created_at=CREATED,
    )
    assert run.summary is not None
    assert run.summary.minimum >= 0
    assert run.summary.maximum <= 10


def test_parameter_mismatch_releases_insufficient_evidence() -> None:
    run = run_monte_carlo(
        run_id="simulation.missing-parameter",
        model=model(),
        parameters=parameters()[:-1],
        config=SimulationConfig(iterations=100),
        created_at=CREATED,
    )
    assert run.status is SimulationStatus.INSUFFICIENT_EVIDENCE
    assert run.failure_reason
    assert run.summary is None


def test_duplicate_runtime_parameter_ids_fail_safely() -> None:
    with pytest.raises(AnalysisError, match="must be unique"):
        run_monte_carlo(
            run_id="simulation.duplicates",
            model=model(),
            parameters=[parameters()[0], parameters()[0], *parameters()[1:]],
            config=SimulationConfig(iterations=100),
            created_at=CREATED,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"kind": "fixed"}, "fixed_value"),
        ({"kind": "uniform", "minimum": 2, "maximum": 1}, "minimum < maximum"),
        (
            {"kind": "triangular", "minimum": 0, "mode": 3, "maximum": 2},
            "minimum <= mode <= maximum",
        ),
        ({"kind": "normal", "mean": 0}, "mean and standard_deviation"),
        ({"kind": "bernoulli"}, "probability"),
        ({"kind": "empirical"}, "require values"),
    ],
)
def test_distribution_contracts_require_kind_specific_parameters(
    payload: dict[str, object], message: str
) -> None:
    base = {
        "parameter_id": "invalid",
        "unit": "unit",
        "evidence_type": "proposed",
        "assumptions": ["Fixture."],
        "limitations": ["Invalid fixture."],
    }
    with pytest.raises(ValidationError, match=message):
        ParameterDistribution.model_validate({**base, **payload})


def test_distribution_evidence_and_finite_value_gates() -> None:
    payload = parameter("x", DistributionKind.FIXED, fixed_value=1).model_dump()
    payload["evidence_type"] = "observed"
    with pytest.raises(ValidationError, match="estimated or proposed"):
        ParameterDistribution.model_validate(payload)
    payload["evidence_type"] = "estimated"
    payload["source_refs"] = []
    with pytest.raises(ValidationError, match="require source references"):
        ParameterDistribution.model_validate(payload)
    payload["fixed_value"] = float("nan")
    with pytest.raises(ValidationError, match="finite number"):
        ParameterDistribution.model_validate(payload)
    payload = parameter(
        "empirical", DistributionKind.EMPIRICAL, empirical_values=[1, 2]
    ).model_dump()
    payload["empirical_values"] = [1, float("inf")]
    with pytest.raises(ValidationError, match="finite number"):
        ParameterDistribution.model_validate(payload)
    payload = parameter("x", DistributionKind.FIXED, fixed_value=1).model_dump()
    payload["source_refs"] *= 2
    with pytest.raises(ValidationError, match="references must be unique"):
        ParameterDistribution.model_validate(payload)
    with pytest.raises(ValidationError, match="minimum cannot exceed"):
        parameter(
            "normal",
            DistributionKind.NORMAL,
            mean=0,
            standard_deviation=1,
            minimum=2,
            maximum=1,
        )


def test_config_model_and_term_validation() -> None:
    with pytest.raises(ValidationError, match="sorted and unique"):
        SimulationConfig(quantiles=[0.9, 0.5])
    with pytest.raises(ValidationError, match="strictly between"):
        SimulationConfig(quantiles=[0])
    with pytest.raises(ValidationError, match="parameter ids must be unique"):
        SimulationModel(
            **{
                **model().model_dump(),
                "terms": [
                    SimulationTerm(parameter_id="x", coefficient=1),
                    SimulationTerm(parameter_id="x", coefficient=2),
                ],
            }
        )
    with pytest.raises(ValidationError, match="floor cannot exceed"):
        SimulationModel(**{**model().model_dump(), "floor": 2, "ceiling": 1})
    with pytest.raises(ValidationError, match="finite number"):
        SimulationTerm(parameter_id="x", coefficient=float("inf"))
    with pytest.raises(ValidationError, match="finite number"):
        SimulationModel(**{**model().model_dump(), "intercept": float("nan")})
    with pytest.raises(ValidationError, match="finite number"):
        SimulationConfig(threshold=float("inf"))

    summary = completed_run().summary
    assert summary is not None
    payload = summary.model_dump()
    payload["minimum"] = payload["mean"] + 1
    with pytest.raises(ValidationError, match="mean must lie"):
        simulation.SimulationSummary.model_validate(payload)
    payload = summary.model_dump()
    payload["quantiles"].append(payload["quantiles"][0])
    with pytest.raises(ValidationError, match="quantiles must be sorted and unique"):
        simulation.SimulationSummary.model_validate(payload)


def test_low_level_quantile_correlation_and_outcome_guards() -> None:
    with pytest.raises(AnalysisError, match="require values"):
        simulation._quantile([], 0.5)
    assert simulation._quantile([0, 10], 0.25) == 2.5
    with pytest.raises(AnalysisError, match="aligned"):
        simulation._correlation([1], [])
    assert simulation._correlation([1, 1], [2, 3]) == 0
    assert simulation._correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1)

    generator = simulation.random.Random(5)
    assert (
        simulation._sample(parameter("fixed", DistributionKind.FIXED, fixed_value=2), generator)
        == 2
    )
    normal = parameter(
        "normal",
        DistributionKind.NORMAL,
        mean=100,
        standard_deviation=1,
        minimum=0,
        maximum=1,
    )
    assert simulation._sample(normal, generator) == 1
    low_normal = parameter(
        "low-normal",
        DistributionKind.NORMAL,
        mean=-100,
        standard_deviation=1,
        minimum=0,
        maximum=1,
    )
    assert simulation._sample(low_normal, generator) == 0
    assert (
        simulation._outcome(
            SimulationModel(
                model_id="floor.model",
                scenario_ref="floor.scenario",
                outcome_id="floor-outcome",
                outcome_unit="unit",
                intercept=-10,
                terms=[SimulationTerm(parameter_id="x", coefficient=1)],
                floor=0,
                method="Floor qualification.",
                assumptions=["Fixture."],
                limitations=["Fixture."],
            ),
            {"x": 1},
        )
        == 0
    )
    nonfinite_model = SimulationModel(
        model_id="nonfinite.model",
        scenario_ref="nonfinite.scenario",
        outcome_id="nonfinite-outcome",
        outcome_unit="unit",
        intercept=1e308,
        terms=[SimulationTerm(parameter_id="x", coefficient=1e308)],
        method="Overflow qualification.",
        assumptions=["Fixture."],
        limitations=["Fixture."],
    )
    with pytest.raises(AnalysisError, match="non-finite outcome"):
        simulation._outcome(nonfinite_model, {"x": 2})


def test_monte_carlo_without_threshold_keeps_probability_absent() -> None:
    run = run_monte_carlo(
        run_id="simulation.no-threshold",
        model=model(),
        parameters=parameters(),
        config=SimulationConfig(iterations=100, random_seed=1, threshold=None),
        created_at=CREATED,
    )
    assert run.summary is not None
    assert run.summary.threshold_probability is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(evidence_type="estimated"),
            "retain simulated evidence type",
        ),
        (
            lambda payload: payload.update(summary=None),
            "require summary and draw hash",
        ),
        (
            lambda payload: payload["parameters"].pop(),
            "exactly match model terms",
        ),
        (
            lambda payload: payload["parameters"].append(payload["parameters"][0]),
            "parameter ids must be unique",
        ),
        (
            lambda payload: payload["sensitivity"].pop(),
            "sensitivity for every parameter",
        ),
        (
            lambda payload: payload["sensitivity"].__setitem__(1, payload["sensitivity"][0]),
            "sensitivity must exactly cover unique parameters",
        ),
        (
            lambda payload: payload["sensitivity"][0].update(absolute_rank=2),
            "sensitivity ranks must be complete and unique",
        ),
        (
            lambda payload: payload["retained_draws"].pop(),
            "configured retained draws",
        ),
        (
            lambda payload: payload["retained_draws"][0].update(iteration=2),
            "ordered stream prefix",
        ),
        (
            lambda payload: payload["retained_draws"][0]["parameters"].pop("shock"),
            "exactly cover parameters",
        ),
        (
            lambda payload: payload["summary"]["quantiles"][0].update(probability=0.01),
            "quantiles must match configuration",
        ),
        (
            lambda payload: payload["summary"].update(threshold_probability=None),
            "threshold probability must match configuration",
        ),
        (
            lambda payload: payload.update(failure_reason="not allowed"),
            "cannot have a failure reason",
        ),
    ],
)
def test_completed_simulation_contract_rejects_claim_and_output_drift(
    mutation: object, message: str
) -> None:
    payload = completed_run().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        SimulationRun.model_validate(payload)


def test_insufficient_simulation_contract_rejects_summary_or_missing_reason() -> None:
    run = run_monte_carlo(
        run_id="simulation.insufficient.contract",
        model=model(),
        parameters=parameters()[:-1],
        config=SimulationConfig(iterations=100),
        created_at=CREATED,
    )
    payload = run.model_dump(mode="json")
    payload["draw_stream_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="cannot emit"):
        SimulationRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["sensitivity"] = completed_run().model_dump(mode="json")["sensitivity"]
    with pytest.raises(ValidationError, match="cannot emit"):
        SimulationRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["failure_reason"] = None
    with pytest.raises(ValidationError, match="require a failure reason"):
        SimulationRun.model_validate(payload)


def test_retained_draw_and_summary_reject_nonfinite_values() -> None:
    payload = completed_run().retained_draws[0].model_dump()
    payload["outcome"] = float("inf")
    with pytest.raises(ValidationError, match="finite number"):
        simulation.RetainedSimulationDraw.model_validate(payload)
    payload = completed_run().retained_draws[0].model_dump()
    payload["parameters"]["shock"] = float("nan")
    with pytest.raises(ValidationError, match="finite number"):
        simulation.RetainedSimulationDraw.model_validate(payload)
    summary = completed_run().summary
    assert summary is not None
    payload = summary.model_dump()
    payload["mean"] = float("inf")
    with pytest.raises(ValidationError, match="finite number"):
        simulation.SimulationSummary.model_validate(payload)
