from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from civicdecision.analysis import causal
from civicdecision.analysis.causal import (
    CausalRunStatus,
    DiagnosticStatus,
    DifferenceInDifferencesConfig,
    DifferenceInDifferencesDesign,
    DifferenceInDifferencesRun,
    PanelObservation,
    run_difference_in_differences,
)
from civicdecision.errors import AnalysisError
from civicdecision.protocols.evidence import EvidenceType

CREATED = datetime(2025, 1, 1, tzinfo=UTC)


def design() -> DifferenceInDifferencesDesign:
    return DifferenceInDifferencesDesign(
        study_id="synthetic.did.qualification",
        estimand="Average effect on treated synthetic units during periods 4 and 5.",
        treatment_definition=(
            "Synthetic treated group receives an additive outcome shift at period 4."
        ),
        comparison_definition="Synthetic never-treated group follows the untreated trend.",
        assignment_mechanism="Deterministic qualification fixture assignment by unit prefix.",
        no_anticipation_rationale="The fixture applies no treatment shift before period 4.",
        parallel_trends_rationale="Both groups share the same deterministic pre-period slope.",
        no_interference_rationale="Fixture outcomes are generated independently by unit.",
        source_refs=["synthetic-fixture.did-panel"],
        limitations=["Synthetic qualification evidence is not a real policy study."],
    )


def config() -> DifferenceInDifferencesConfig:
    return DifferenceInDifferencesConfig(
        intervention_period=4,
        minimum_units_per_group=5,
        minimum_pre_periods=4,
        minimum_post_periods=2,
        pretrend_slope_equivalence_margin=0.2,
        placebo_effect_equivalence_margin=0.5,
    )


def panel(
    *, treatment_effect: float = 3.0, pretrend_difference: float = 0.0
) -> list[PanelObservation]:
    rows = []
    for treated in (False, True):
        for unit_index in range(6):
            unit = f"{'treated' if treated else 'comparison'}-{unit_index}"
            unit_offset = unit_index * 0.4
            for period in range(6):
                outcome = 10 + unit_offset + period
                if treated:
                    outcome += pretrend_difference * min(period, 3)
                    if period >= 4:
                        outcome += treatment_effect
                rows.append(
                    PanelObservation(
                        unit_id=unit,
                        period=period,
                        outcome=outcome,
                        treated_group=treated,
                    )
                )
    return rows


def passing_run() -> DifferenceInDifferencesRun:
    return run_difference_in_differences(
        run_id="causal.did.passing",
        design=design(),
        observations=panel(),
        config=config(),
        created_at=CREATED,
    )


def test_passing_design_releases_conditional_causal_estimate() -> None:
    run = passing_run()
    assert run.status is CausalRunStatus.IDENTIFICATION_PASSED
    assert run.evidence_type is EvidenceType.CAUSAL
    assert run.causal_claim_issued
    assert run.primary_effect is not None
    assert run.primary_effect.estimate == pytest.approx(3)
    assert len(run.event_time_effects) == 2
    assert len(run.placebo_effects) == 3
    assert all(item.status is DiagnosticStatus.PASS for item in run.diagnostics)
    assert "conditional" in run.interpretation.lower()


def test_failed_pretrend_is_preserved_but_not_labeled_causal() -> None:
    run = run_difference_in_differences(
        run_id="causal.did.failed-pretrend",
        design=design(),
        observations=panel(pretrend_difference=1.0),
        config=config(),
        created_at=CREATED,
    )
    assert run.status is CausalRunStatus.INSUFFICIENT_EVIDENCE
    assert run.evidence_type is EvidenceType.ESTIMATED
    assert not run.causal_claim_issued
    assert run.primary_effect is not None
    assert run.failure_reason
    assert any(item.status is DiagnosticStatus.FAIL for item in run.diagnostics)


def test_small_or_unbalanced_panel_fails_before_effect_estimation() -> None:
    small = [item for item in panel() if not item.unit_id.endswith(("-4", "-5"))]
    run = run_difference_in_differences(
        run_id="causal.did.small",
        design=design(),
        observations=small,
        config=config(),
        created_at=CREATED,
    )
    assert run.status is CausalRunStatus.INSUFFICIENT_EVIDENCE
    assert run.primary_effect is None
    assert "unit-count" in (run.failure_reason or "")

    unbalanced = panel()
    unbalanced.pop()
    run = run_difference_in_differences(
        run_id="causal.did.unbalanced",
        design=design(),
        observations=unbalanced,
        config=config(),
        created_at=CREATED,
    )
    assert any(
        item.id == "balanced-panel" and item.status is DiagnosticStatus.FAIL
        for item in run.diagnostics
    )


def test_run_hash_is_deterministic() -> None:
    assert passing_run().content_hash() == passing_run().content_hash()


@pytest.mark.parametrize(
    ("observations", "message"),
    [
        ([], "requires panel observations"),
        ([*panel(), panel()[0]], "keys must be unique"),
    ],
)
def test_panel_input_guards(observations: list[PanelObservation], message: str) -> None:
    with pytest.raises(AnalysisError, match=message):
        run_difference_in_differences(
            run_id="causal.did.invalid",
            design=design(),
            observations=observations,
            config=config(),
            created_at=CREATED,
        )


def test_assignment_must_be_constant_within_unit() -> None:
    observations = panel()
    changed = observations[0].model_copy(update={"treated_group": True})
    observations[0] = changed
    with pytest.raises(AnalysisError, match="constant within unit"):
        run_difference_in_differences(
            run_id="causal.did.assignment-drift",
            design=design(),
            observations=observations,
            config=config(),
            created_at=CREATED,
        )


def test_panel_outcome_and_design_source_validation() -> None:
    with pytest.raises(ValidationError, match="finite"):
        PanelObservation(unit_id="a", period=0, outcome=float("nan"), treated_group=True)
    payload = design().model_dump()
    payload["source_refs"] *= 2
    with pytest.raises(ValidationError, match="must be unique"):
        DifferenceInDifferencesDesign.model_validate(payload)
    with pytest.raises(ValidationError, match="requires a balanced panel"):
        DifferenceInDifferencesConfig(
            intervention_period=4,
            pretrend_slope_equivalence_margin=1,
            placebo_effect_equivalence_margin=1,
            require_balanced_panel=False,
        )


def test_low_level_estimation_guards_and_zero_variance_p_values() -> None:
    with pytest.raises(AnalysisError, match="at least two"):
        causal._sample_variance([1])
    with pytest.raises(AnalysisError, match="two units"):
        causal._estimate("bad", [1], [1, 2], 0.95)
    with pytest.raises(AnalysisError, match="aligned"):
        causal._slope([0], [1])
    with pytest.raises(AnalysisError, match="must vary"):
        causal._slope([1, 1], [1, 2])
    null = causal._estimate("null", [1, 1], [1, 1], 0.95)
    nonnull = causal._estimate("nonnull", [2, 2], [1, 1], 0.95)
    assert null.p_value == 1
    assert nonnull.p_value == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(evidence_type="estimated"),
            "explicit causal evidence type",
        ),
        (
            lambda payload: payload.update(causal_claim_issued=False),
            "explicit causal evidence type",
        ),
        (
            lambda payload: payload.update(primary_effect=None),
            "requires effect estimates",
        ),
        (
            lambda payload: payload.update(failure_reason="not allowed"),
            "cannot have a failure reason",
        ),
        (
            lambda payload: payload["diagnostics"][0].update(status="fail"),
            "cannot contain failed diagnostics",
        ),
        (
            lambda payload: payload["diagnostics"].append(payload["diagnostics"][0]),
            "diagnostic ids must be unique",
        ),
    ],
)
def test_causal_run_contract_rejects_claim_upgrades_and_drift(
    mutation: object, message: str
) -> None:
    payload = passing_run().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        DifferenceInDifferencesRun.model_validate(payload)


def test_insufficient_run_cannot_be_upgraded_to_causal() -> None:
    run = run_difference_in_differences(
        run_id="causal.did.failed-contract",
        design=design(),
        observations=panel(pretrend_difference=1.0),
        config=config(),
        created_at=CREATED,
    )
    payload = run.model_dump(mode="json")
    payload["evidence_type"] = "causal"
    payload["causal_claim_issued"] = True
    with pytest.raises(ValidationError, match="estimated associations"):
        DifferenceInDifferencesRun.model_validate(payload)

    payload = run.model_dump(mode="json")
    payload["failure_reason"] = None
    with pytest.raises(ValidationError, match="require a failure reason"):
        DifferenceInDifferencesRun.model_validate(payload)


def test_effect_interval_must_contain_estimate() -> None:
    payload = passing_run().primary_effect.model_dump()  # type: ignore[union-attr]
    payload["lower"] = payload["estimate"] + 1
    with pytest.raises(ValidationError, match="must contain"):
        causal.EffectEstimate.model_validate(payload)
